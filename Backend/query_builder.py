"""
Turns a validated GISQuery into parameterized PostGIS SQL (raw psycopg2, no ORM).

The LLM never writes SQL. Every layer and column name is checked against the real
database schema and quoted as an identifier; every value goes through a %s parameter.
"""
import json

from psycopg2 import sql

import config
import db
from schemas import Filter, GISQuery, SpatialCondition

# "place" is a pseudo-layer the LLM uses for a bare name like "Thrissur" or "Vaikom".
# It is expanded to a search across all boundary layers (smallest first).
PLACE = "place"
PLACE_LAYERS = ("towns", "city", "districts", "state")

POINT = "point"   # the spot the user clicked with "Select on map" (coordinates come from the request)

PROXIMITY_OPS = ("dwithin", "near", "within_distance")
INTERSECT_OPS = ("intersects", "within", "contains")

# Extra map layers (reference features + buffer area) for "within distance" searches
ENABLE_OVERLAY = True
OVERLAY_MAX_REFS = 300


def _columns(schema_info: dict, layer: str) -> dict:
    return {c["name"].lower(): c for c in schema_info[layer]["columns"]}


def _geom_col(schema_info: dict, layer: str) -> str:
    cols = _columns(schema_info, layer)
    return next(
        (c["name"] for c in cols.values() if c["type"].lower() in ("geometry", "geography", "user-defined")),
        config.GEOM_COLUMN,
    )


def _require_layer(schema_info: dict, layer, label: str):
    if layer not in schema_info:
        raise ValueError(f"Unknown {label} layer '{layer}'. Available layers: {', '.join(schema_info)}")


def _has_columns(schema_info: dict, layer: str, filters) -> bool:
    cols = _columns(schema_info, layer)
    return all(f.column.lower() in cols for f in filters)


def _resolve_target_place(query: GISQuery, schema_info: dict) -> str:
    """target_layer 'place' ("show the boundary of Kalamassery") -> the first boundary layer that has that name."""
    name = next(
        (str(f.value) for f in query.filters if f.column.lower() == "name" and not isinstance(f.value, list)),
        None,
    )
    if not name:
        raise ValueError("Please tell me which place you mean.")

    for exact in (True, False):  # exact match across all layers first, then "contains"
        for layer in PLACE_LAYERS:
            if layer not in schema_info:
                continue
            cond = sql.SQL("lower(name::text) = lower(%s)") if exact else sql.SQL("name::text ILIKE %s")
            value = name.strip() if exact else f"%{name.strip()}%"
            found = db.fetch_value(
                sql.SQL("SELECT 1 FROM {}.{} WHERE ").format(
                    sql.Identifier(config.DB_SCHEMA), sql.Identifier(layer)
                )
                + cond
                + sql.SQL(" LIMIT 1"),
                (value,),
            )
            if found:
                return layer
    raise ValueError(f'I could not find a town, city, district or state called "{name}".')


def _filter_sql(alias: str, flt: Filter, layer: str, schema_info: dict):
    cols = _columns(schema_info, layer)
    col = cols.get(flt.column.lower())
    if col is None:
        raise ValueError(
            f"Layer '{layer}' has no column '{flt.column}'. "
            f"Columns: {', '.join(c['name'] for c in cols.values())}"
        )

    ident = sql.SQL("{}.{}").format(sql.Identifier(alias), sql.Identifier(col["name"]))
    is_text = col["type"] in config.TEXT_TYPES
    op, value = flt.operator.lower().strip(), flt.value

    if isinstance(value, list):
        if op == "=":
            op = "in"
        elif op == "!=":
            op = "not in"
        elif op != "in":
            raise ValueError(f"Operator '{op}' cannot be used with a list of values")

    if op in ("in", "not in"):
        values = value if isinstance(value, list) else [value]
        clause = sql.SQL("lower({}::text) = ANY(%s)").format(ident)
        if op == "not in":
            clause = sql.SQL("NOT (") + clause + sql.SQL(")")
        return clause, [[str(v).lower() for v in values]]

    if op in ("ilike", "contains", "like") or (col["name"].lower() == "name" and op == "="):
        clean_val = str(value).strip("%")
        return sql.SQL("{}::text ILIKE %s").format(ident), [f"%{clean_val}%"]

    if is_text and op in ("=", "!="):
        return sql.SQL("lower({}) {} lower(%s)").format(ident, sql.SQL(op)), [str(value)]

    return sql.SQL("{} {} %s").format(ident, sql.SQL(op)), [value]


def _ref_where(cond: SpatialCondition, ref_layer: str, schema_info: dict, location=None):
    clauses, params = [], []
    for flt in cond.reference_filters:
        c, p = _filter_sql("r", flt, ref_layer, schema_info)
        clauses.append(c)
        params.extend(p)

    # "banks in this town": boundary layer with no name filter + a selected location
    if location is not None and not cond.reference_filters and ref_layer in PLACE_LAYERS:
        clauses.append(sql.SQL(
            "ST_Intersects(r.{g}, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
        ).format(g=sql.Identifier(_geom_col(schema_info, ref_layer))))
        params.extend([location.lon, location.lat])

    where_sql = sql.SQL("WHERE ") + sql.SQL(" AND ").join(clauses) if clauses else sql.SQL("")
    return where_sql, params


def _single_spatial_exists(cond: SpatialCondition, ref_layer: str, schema_info: dict):
    op = cond.operation.lower().strip()

    if op in PROXIMITY_OPS or op in INTERSECT_OPS:
        spatial_sql = sql.SQL(
            "EXISTS ("
            "SELECT 1 FROM __ref_geom rb "
            "WHERE ST_Intersects(t.{target_geom}, rb.geom)"
            ")"
        ).format(target_geom=sql.Identifier(config.GEOM_COLUMN))
        return spatial_sql, []

    raise ValueError(f"Unsupported spatial operation: {cond.operation}")


def _spatial_sql(cond: SpatialCondition, schema_info: dict):
    ref = cond.reference_layer
    if ref not in (PLACE, POINT):  # "place" is not a real table, it is expanded in run_query
        _require_layer(schema_info, ref, "reference")
    clause, params = _single_spatial_exists(cond, ref, schema_info)
    if cond.negate:
        clause = sql.SQL("NOT ") + clause
    return clause, params


def _build_overlay(cond, ref_layers, target_features, schema_info):
    """Extra map layers for a 'within distance' search: the reference features and the buffer area."""
    distance = float(cond.distance_m or 1500.0)
    shown = [json.dumps(f["geometry"]) for f in target_features if f.get("geometry")]
    if not shown:
        return None

    # 1. reference features within the distance of at least one result that is shown on the map
    ref_features = []
    for r_lyr in ref_layers:
        left = OVERLAY_MAX_REFS - len(ref_features)
        if left <= 0:
            break
        r_geom = _geom_col(schema_info, r_lyr)

        clauses, r_params = [], []
        for flt in cond.reference_filters:
            c, p = _filter_sql("r", flt, r_lyr, schema_info)
            clauses.append(c)
            r_params.extend(p)
        clauses.append(sql.SQL(
            "EXISTS (SELECT 1 FROM __shown s "
            "WHERE ST_DWithin(s.geom::geography, r.{rg}::geography, %s))"
        ).format(rg=sql.Identifier(r_geom)))

        ref_sql = (
            sql.SQL(
                "WITH __shown AS ("
                "SELECT ST_SetSRID(ST_GeomFromGeoJSON(g), 4326) AS geom FROM unnest(%s::text[]) AS g) "
                "SELECT jsonb_build_object('type', 'Feature', "
                "'geometry', ST_AsGeoJSON(r.{rg}, 6)::jsonb, "
                "'properties', to_jsonb(r) - {rg_name}) AS feature "
                "FROM {r_table} r WHERE "
            ).format(
                rg=sql.Identifier(r_geom),
                rg_name=sql.Literal(r_geom),
                r_table=sql.Identifier(config.DB_SCHEMA, r_lyr),
            )
            + sql.SQL(" AND ").join(clauses)
            + sql.SQL(" LIMIT %s")
        )

        rows = db.fetch_all(ref_sql, [shown] + r_params + [distance, left])
        ref_features.extend(row["feature"] for row in rows)

    # 2. buffer around whichever side has fewer features (clearer on the map)
    around = "reference" if ref_features and len(ref_features) <= len(target_features) else "target"
    anchors = ref_features if around == "reference" else target_features
    geoms = [json.dumps(f["geometry"]) for f in anchors if f.get("geometry")]

    buffer_feature = None
    if geoms:
        raw = db.fetch_value(
            "SELECT ST_AsGeoJSON(ST_Union(ST_Buffer(ST_SetSRID(ST_GeomFromGeoJSON(g), 4326)::geography, %s)::geometry), 6) "
            "FROM unnest(%s::text[]) AS g",
            (distance, geoms),
        )
        if raw:
            buffer_feature = {
                "type": "Feature",
                "geometry": json.loads(raw),
                "properties": {"distance_m": distance, "around": around},
            }

    label = ", ".join(
        str(v) for f in cond.reference_filters for v in (f.value if isinstance(f.value, list) else [f.value])
    )
    return {
        "around": around,
        "distance_m": distance,
        "reference_label": label,
        "capped": len(ref_features) >= OVERLAY_MAX_REFS,
        "buffer": buffer_feature,
        "references": {"type": "FeatureCollection", "features": ref_features},
    }
def _point_overlay(location, distance):
    """Buffer circle around the selected point, drawn even when nothing was found."""
    raw = db.fetch_value(
        "SELECT ST_AsGeoJSON(ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)::geometry, 6)",
        (location.lon, location.lat, distance),
    )
    if not raw:
        return None
    return {
        "around": "point",
        "distance_m": distance,
        "reference_label": "the selected location",
        "capped": False,
        "buffer": {"type": "Feature", "geometry": json.loads(raw), "properties": {"distance_m": distance}},
        "references": {"type": "FeatureCollection", "features": []},
    }

def run_query(query: GISQuery, schema_info: dict, location=None) -> dict:
    """Execute the query and return {sql, total, returned, geojson, overlay}."""
    limit = query.limit if query.limit and query.limit > 0 else config.DEFAULT_LIMIT
    limit = min(limit, config.MAX_LIMIT)

    if query.target_layer == PLACE:
        query.target_layer = _resolve_target_place(query, schema_info)
    target = query.target_layer
    _require_layer(schema_info, target, "target")

    cte_sql = sql.SQL("")
    cte_params = []
    ref_layers = []

    if query.spatial:
        cond = query.spatial[0]
        ref = cond.reference_layer
        op = cond.operation.lower().strip()

        if ref == POINT:
            if location is None:
                raise ValueError("Click 'Select on map' and choose a location first.")
            ref_layers = [POINT]
        elif ref == PLACE:
            # Bare place name: search towns, city, districts and state together (UNION below).
            # Layers that lack a filtered column (e.g. 'district') are skipped, not errors.
            ref_layers = [
                lyr for lyr in PLACE_LAYERS
                if lyr in schema_info and _has_columns(schema_info, lyr, cond.reference_filters)
            ]
            if not ref_layers:
                raise ValueError("None of the boundary layers match that place filter.")
        else:
            _require_layer(schema_info, ref, "reference")
            ref_layers = [ref]

        cte_unions = []
        for r_lyr in ref_layers:
            if r_lyr == POINT:
                if op in PROXIMITY_OPS:
                    cte_params.extend([location.lon, location.lat, float(cond.distance_m or 1500.0)])
                    cte_unions.append(sql.SQL(
                        "SELECT ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)::geometry AS geom"
                    ))
                else:  # "which district is this?": the point itself
                    cte_params.extend([location.lon, location.lat])
                    cte_unions.append(sql.SQL("SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326) AS geom"))
                continue
            r_geom = _geom_col(schema_info, r_lyr)
            r_where_sql, r_params = _ref_where(cond, r_lyr, schema_info)

            if op in PROXIMITY_OPS:
                distance = float(cond.distance_m or 1500.0)
                cte_params.append(distance)
                cte_params.extend(r_params)

                cte_unions.append(sql.SQL(
                    "SELECT ST_Buffer(r.{r_geom}::geography, %s)::geometry AS geom "
                    "FROM {r_table} r {r_where}"
                ).format(
                    r_geom=sql.Identifier(r_geom),
                    r_table=sql.Identifier(config.DB_SCHEMA, r_lyr),
                    r_where=r_where_sql,
                ))
            elif op in INTERSECT_OPS:
                cte_params.extend(r_params)
                cte_unions.append(sql.SQL(
                    "SELECT r.{r_geom} AS geom "
                    "FROM {r_table} r {r_where}"
                ).format(
                    r_geom=sql.Identifier(r_geom),
                    r_table=sql.Identifier(config.DB_SCHEMA, r_lyr),
                    r_where=r_where_sql,
                ))

        if cte_unions:
            union_sql = sql.SQL(" UNION ALL ").join(cte_unions)
            cte_sql = sql.SQL(
                "WITH __ref_geom AS MATERIALIZED ({union_sql}) "
            ).format(union_sql=union_sql)

    # Build WHERE clauses
    where_parts, where_params = [], []

    for flt in query.filters:
        clause, p = _filter_sql("t", flt, target, schema_info)
        where_parts.append(clause)
        where_params.extend(p)

    for cond in query.spatial:
        clause, p = _spatial_sql(cond, schema_info)
        where_parts.append(clause)
        where_params.extend(p)

    where = sql.SQL(" AND ").join(where_parts) if where_parts else sql.SQL("TRUE")
    params = cte_params + where_params

    table = sql.SQL("{}.{}").format(sql.Identifier(config.DB_SCHEMA), sql.Identifier(target))
    target_geom = _geom_col(schema_info, target)

    count_sql = cte_sql + sql.SQL("SELECT count(*) FROM {table} t WHERE {where}").format(
        table=table, where=where
    )

    data_sql = cte_sql + sql.SQL(
        "SELECT jsonb_build_object("
        "'type', 'Feature', "
        "'geometry', ST_AsGeoJSON(t.{geom}, 6)::jsonb, "
        "'properties', to_jsonb(t) - {geom_name}"
        ") AS feature "
        "FROM {table} t WHERE {where} LIMIT %s"
    ).format(
        geom=sql.Identifier(target_geom),
        geom_name=sql.Literal(target_geom),
        table=table,
        where=where,
    )

    rendered_sql = db.render_sql(data_sql, params + [limit])

    print("\n" + "=" * 60)
    print("🗺️ [POSTGIS RENDERED SQL QUERY]:")
    print("=" * 60)
    print(rendered_sql)
    print("=" * 60 + "\n")

    total = db.fetch_value(count_sql, params)
    rows = db.fetch_all(data_sql, params + [limit])
    features = [row["feature"] for row in rows]

    # Optional extra map layers; a failure here must never break the main result
    overlay = None
    if ENABLE_OVERLAY and query.spatial and ref_layers:
        first = query.spatial[0]
        if first.operation.lower().strip() in PROXIMITY_OPS and not first.negate:
            try:
                if ref_layers == [POINT]:
                    overlay = _point_overlay(location, float(first.distance_m or 1500.0))
                elif features:
                    overlay = _build_overlay(first, ref_layers, features, schema_info)
            except Exception as err:
                print(f"[overlay skipped] {err}")

    return {
        "sql": rendered_sql,
        "total": total,
        "returned": len(features),
        "geojson": {"type": "FeatureCollection", "features": features},
        "overlay": overlay,
    }