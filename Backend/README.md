# GeoMind GIS Assistant

Ask questions in plain English; llama3.1 (Ollama) turns them into a structured query,
the backend builds parameterized PostGIS SQL (raw psycopg2, no ORM) and the map shows the result.

```
Browser (Leaflet)  ->  FastAPI  ->  Ollama llama3.1   (text -> JSON, never SQL)
                           |
                           +-----> PostgreSQL/PostGIS (gisdb, schema postgres)
```

## Setup

1. Pull the model:   `ollama pull llama3.1`
2. Create a virtual environment and install packages:
   ```
   python -m venv venv
   venv\Scripts\activate          (Windows)   |   source venv/bin/activate   (Linux/macOS)
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set your password.
4. Run `setup.sql` once in pgAdmin (spatial indexes).
5. Start the server:   `uvicorn main:app --reload --port 8000`
   (GeoServer already uses 8080, so this app uses 8000.)
6. Open http://localhost:8000

## Check each piece separately

| URL | What it tells you |
|---|---|
| `GET /api/health` | PostGIS version, Ollama online, model installed |
| `GET /api/layers` | Columns and category values exactly as the AI sees them |
| `GET /api/data/poi?limit=50` | Raw layer preview as GeoJSON |
| `POST /api/interpret` `{"text": "..."}` | AI step only, nothing executed |
| `POST /api/execute` (JSON from the step above) | SQL step only |
| `POST /api/ask` `{"text": "..."}` | Full pipeline |

Interactive docs: http://localhost:8000/docs

## Files

| File | Role |
|---|---|
| `config.py` | Settings, layer list, limits |
| `db.py` | Connection pool, read-only raw SQL helpers, schema introspection |
| `schemas.py` | Pydantic models for the AI's JSON output |
| `ai_service.py` | Prompt + Ollama call + validation |
| `query_builder.py` | JSON -> safe parameterized SQL |
| `main.py` | FastAPI endpoints |
| `index.html` | Map UI |

## Tuning

* Wrong results usually mean the prompt does not know your data. Open `/api/layers`
  and check that `fclass` values look right (e.g. `hospital`, `school`).
* Example prompts in `ai_service.py` use `fclass` values `hospital`, `school`, `primary`.
  If your data uses other values, edit the examples.
* Need a stronger model? Set `OLLAMA_MODEL` in `.env` (e.g. `qwen2.5:14b`). No code change needed.
