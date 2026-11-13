-- Run once in pgAdmin (Query Tool on database gisdb).
-- Plain spatial index: used by ST_Intersects.
CREATE INDEX IF NOT EXISTS buildings_shape_gix ON postgres.buildings USING GIST (shape);
CREATE INDEX IF NOT EXISTS poi_shape_gix       ON postgres.poi       USING GIST (shape);
CREATE INDEX IF NOT EXISTS roads_shape_gix     ON postgres.roads     USING GIST (shape);

-- Geography-expression index: makes "within X meters" (ST_DWithin on ::geography) fast.
CREATE INDEX IF NOT EXISTS buildings_shape_geog_gix ON postgres.buildings USING GIST ((shape::geography));
CREATE INDEX IF NOT EXISTS poi_shape_geog_gix       ON postgres.poi       USING GIST ((shape::geography));
CREATE INDEX IF NOT EXISTS roads_shape_geog_gix     ON postgres.roads     USING GIST ((shape::geography));

ANALYZE postgres.buildings;
ANALYZE postgres.poi;
ANALYZE postgres.roads;

-- Look at your real columns (the app also reads these automatically):
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'postgres' AND table_name IN ('buildings', 'poi', 'roads')
ORDER BY table_name, ordinal_position;
