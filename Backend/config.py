import os

from dotenv import load_dotenv

load_dotenv()

# --- PostgreSQL / PostGIS -------------------------------------------------
DB = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "gisdb"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}
DB_SCHEMA = os.getenv("DB_SCHEMA", "postgres")

# --- Ollama ----------------------------------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# --- GIS layers (table names inside DB_SCHEMA) -----------------------------
GEOM_COLUMN = "shape"  # geometry column written by ArcGIS Pro (SRID 4326)

LAYERS = {
    "buildings": {
        "geometry": "Polygon",
        "description": "Building footprints with name and type (e.g. temple, school)",
    },
    "poi": {
        "geometry": "Point",
        "description": "Points of interest with fclass (hospital, school, bank, atm, etc.) and name",
    },
    "roads": {
        "geometry": "LineString",
        "description": "Road network with fclass, name, ref, bridge (T/F), and tunnel (T/F)",
    },
    "state": {
        "geometry": "Polygon",
        "description": "state boundary with name field",
    },
    "districts": {
        "geometry": "Polygon",
        "description": "district boundaries with name field",
    },
    "city": {
        "geometry": "Polygon",
        "description": "city boundaries with name field",
    },
    "towns": {
        "geometry": "Polygon",
        "description": "town boundaries; name = town name, district = district the town belongs to, state = state (Kerala)",
    }
}

# --- Limits ----------------------------------------------------------------
DEFAULT_LIMIT = 100
MAX_LIMIT = 5000
MAX_CATEGORY_VALUES = 150  # text columns with <= this many distinct values are shown to the LLM

TEXT_TYPES = {"character varying", "text", "character"}
IGNORED_COLUMNS = {"objectid", "globalid", "gdb_geomattr_data"}
