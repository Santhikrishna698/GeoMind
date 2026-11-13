"""Natural language -> structured GISQuery, using Ollama (llama3.1)."""
import json

import requests
from pydantic import ValidationError

import config
from examples import DEFAULT_NEAR_M, select_examples
from schemas import GISQuery

# Set True to print the full system prompt on every request (very long).
DEBUG_PRINT_PROMPT = False

PROMPT_TEMPLATE = """You are GeoMind, an expert GIS query interpreter and spatial assistant. Convert the user's natural language request into ONE valid JSON object matching the requested schema. Never write SQL. Output raw JSON only.

DATA YOU CAN QUERY
{{LAYERS}}

JSON FIELDS
- target_layer: the layer whose features the user wants returned (one of: poi, buildings, roads, towns, city, districts, state, or "place" - see PLACE RULES).
- filters: attribute conditions on the target layer. Each item: {"column", "operator", "value"}.
  Operators: "=", "!=", ">", "<", ">=", "<=", "ilike" (name contains text), "in" (value is a list).
- spatial: conditions relating the target layer to ANOTHER layer. Each item:
  {"operation", "reference_layer", "distance_m", "reference_filters", "negate"}
  - "within_distance": distance_m is ALWAYS in meters (1 km = 1000). If the user says "near", "nearby" or "around" without a distance, use {{NEAR_M}}.
  - "intersects": features inside / touching the reference layer; distance_m is null.
  - reference_filters: attribute conditions on the reference layer (same format as filters).
  - negate: true for "not near", "far from", "without", "outside", "not in".
- limit: only if the user asks for a specific number (e.g. "first 100", "top 50"), otherwise null.
- requires_clarification / clarification_message: set to true when the request is genuinely ambiguous, needs the user's location, or asks for something the map data cannot answer (population, routes, comparisons). Ask one short, polite question.

GENERAL RULES
1. Use ONLY the layer names, geometry types and column names listed above. For columns with allowed values, use exactly one of those values.
2. Conditions about the target layer itself go in "filters". Conditions about where it is, or its relation to another layer, go in "spatial".
3. Do NOT put a place name in "filters" when the user only says WHERE the features are ("schools in Vaikom"). The place goes in "spatial". Put a name in "filters" only when the user wants that named thing itself ("show Lisie Hospital", "MG Road", "boundary of Vaikom").
4. Roads with numbers like "NH-66" or "SH-49": filter on the `ref` column with "ilike", written with a hyphen.
5. For religious or specific building structures (temples, mosques, churches) when querying `buildings`, filter on the `type` column.
6. Ignore spelling mistakes in category words ("hosptals" means hospitals).

PLACE RULES (boundaries: towns, city, districts, state)
- towns: columns name, district, state (state is always Kerala)
- city: cities / municipalities / localities
- districts: the 14 districts
- state: the state boundary
A. If the user NAMES THE TYPE, use that layer: "district" -> districts; "city", "corporation", "municipality" -> city; "town" -> towns; "state" -> state.
B. If the user gives a BARE place name with no type ("in Kalamassery", "in Vaikom", "in Kottayam"), set reference_layer to "place". Never guess between towns, city and districts yourself: the backend searches all of them.
C. If the user gives a town together with its district, use the towns layer with TWO reference_filters: name and district.
D. Listing boundaries: "towns in Ernakulam district" -> target_layer towns with a filter on the `district` column. "towns in Kerala" -> filter on the `state` column. "districts in Kerala" -> target districts, spatial intersects state Kerala.
E. Showing a boundary itself: if the type is named use that layer, otherwise target_layer "place" with a name filter.
F. "in", "inside", "within the limits of" a place -> operation "intersects". "outside / not in" -> intersects with negate true.
G. "near", "around", "close to" a NAMED THING -> operation "within_distance" with reference_layer "poi" (a landmark such as cusat, infopark, a mall, a hospital). Filter the landmark by `name` with "ilike" and do NOT restrict its fclass unless the user says so. Use a boundary layer for "near" only when the user explicitly says town, city, district or state.
H. "near a hospital" with a distance, or "near any / all hospitals" -> reference_layer "poi" filtered by fclass. "near hospital" with no name, no distance and no "any/all" -> ask which one.
I. A spatial condition may only use ONE reference layer. If the user combines two location conditions, keep the main one (the place) and ignore the other.

CATEGORY WORDS -> fclass (use only values that exist in the allowed list above)
- "medical store", "medical shop", "drug store", "chemist" -> "in": ["pharmacy", "chemist"]
- "doctor", "doctors" -> "in": ["doctors", "clinic"]
- "eateries", "places to eat", "food" -> "in": ["restaurant", "cafe", "fast_food"]
- "stay", "lodging", "accommodation" -> "in": ["hotel", "guesthouse", "hostel"]
- "cash machine", "ATM" -> "atm"
- "police station" -> "police"; "highway" -> "in": ["motorway", "trunk"]
Two or more categories in one request ("ATMs and banks") -> one filter with operator "in".

Worked examples are provided as earlier chat turns. Answer in exactly the same JSON format.
"""
LOCATION_RULES = """
SELECTED LOCATION
The user has clicked a point on the map. Refer to it with reference_layer "point" and reference_filters []. The backend already knows the coordinates; never write coordinates yourself.
- "near", "around", "here", "nearby", "within X km / m of this location", or a bare category with no place named ("schools", "restaurants") -> operation "within_distance", reference_layer "point", distance_m as stated (default {{NEAR_M}}).
- "in this town / city / district / locality / village" -> operation "intersects", reference_layer towns / city / districts, reference_filters []. The backend picks the one that contains the point.
- "which district / town / city / building is this" -> target_layer is that layer, spatial: intersects with reference_layer "point".
- If the user names a place ("in Aluva") or says "all" / "every", ignore the selected location.
"""

NO_LOCATION_RULES = """
No location is selected on the map. Never use reference_layer "point". If the user says "near me", "here" or "this location", ask them to click 'Select on map' first.
"""

def build_system_prompt(schema_info: dict, has_location: bool = False) -> str:
    lines = []
    for layer, meta in schema_info.items():
        lines.append(f'LAYER "{layer}" ({meta["geometry"]}) - {meta["description"]}')
        for col in meta["columns"]:
            line = f'    - {col["name"]} ({col["type"]})'
            if col["values"]:
                line += " allowed values: " + ", ".join(str(v) for v in col["values"])
            lines.append(line)
    return (
        (PROMPT_TEMPLATE+(LOCATION_RULES if has_location else NO_LOCATION_RULES))
        .replace("{{LAYERS}}", "\n".join(lines))
        .replace("{{NEAR_M}}", str(DEFAULT_NEAR_M))
    )


def build_messages(user_text: str, schema_info: dict, has_location: bool = False) -> list:
    messages = [{"role": "system", "content": build_system_prompt(schema_info, has_location)}]
    for e in select_examples(user_text, with_location=has_location):
        messages.append({"role": "user", "content": e.question})
        messages.append({"role": "assistant", "content": json.dumps(e.query)})
    messages.append({"role": "user", "content": user_text})
    return messages


def _chat(messages: list, response_format) -> str:
    response = requests.post(
        f"{config.OLLAMA_URL}/api/chat",
        json={
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": response_format,
            "options": {"temperature": 0, "num_ctx": 8192},
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def interpret(user_text: str, schema_info: dict, has_location: bool = False) -> GISQuery:
    messages = build_messages(user_text, schema_info, has_location)

    # --- CONSOLE DEBUG LOGGING ---
    print("\n" + "=" * 60)
    print(f"🤖 [OLLAMA PROMPT] User Query: '{user_text}'")
    print("   Examples used:")
    for m in messages[1:-1]:
        if m["role"] == "user":
            print(f"     - {m['content']}")
    if DEBUG_PRINT_PROMPT:
        print("=" * 60)
        print(messages[0]["content"])
    print("=" * 60 + "\n")

    try:
        try:
            content = _chat(messages, GISQuery.model_json_schema())
        except requests.HTTPError as err:
            if err.response is not None and err.response.status_code == 400:
                content = _chat(messages, "json")
            else:
                raise

        parsed = json.loads(content)
        print(f"✨ [OLLAMA JSON RESULT]: {json.dumps(parsed, indent=2)}\n", flush=True)
        return GISQuery(**parsed)

    except requests.ConnectionError:
        message = f"Cannot reach Ollama at {config.OLLAMA_URL}. Is it running?"
    except requests.RequestException as err:
        message = f"Ollama request failed: {err}"
    except (json.JSONDecodeError, ValidationError) as err:
        message = f"The model returned an invalid answer, please rephrase. ({err})"

    return GISQuery(requires_clarification=True, clarification_message=message)
