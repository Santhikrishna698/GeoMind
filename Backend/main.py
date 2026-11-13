from contextlib import asynccontextmanager
from pathlib import Path

import psycopg2
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import config
import db
from ai_service import interpret
from query_builder import run_query
from schemas import AskRequest, GISQuery

state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()
    state["schema"] = db.load_schema_info()
    print("Loaded layers:", ", ".join(state["schema"]))
    yield
    db.close_pool()


app = FastAPI(title="GeoMind GIS Assistant", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local development
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "index.html")


@app.get("/api/health")
def health():
    result = {"api": "online"}
    try:
        result["postgis"] = db.fetch_value("SELECT postgis_version()")
    except Exception as err:
        result["postgis"] = f"error: {err}"
    try:
        tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5).json()
        names = [m["name"] for m in tags.get("models", [])]
        result["ollama"] = "online"
        result["model_installed"] = any(n.startswith(config.OLLAMA_MODEL) for n in names)
    except Exception as err:
        result["ollama"] = f"error: {err}"
    return result


@app.get("/api/layers")
def layers():
    """Layers, columns and category values exactly as the AI sees them."""
    return state["schema"]


@app.get("/api/data/{layer}")
def layer_data(layer: str, limit: int = 200):
    """Plain preview of a layer as GeoJSON (no AI involved)."""
    try:
        return run_query(GISQuery(target_layer=layer, limit=limit), state["schema"])["geojson"]
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except psycopg2.Error as err:
        raise HTTPException(status_code=500, detail=f"Database error: {err}")


@app.post("/api/interpret")
def interpret_text(body: AskRequest):
    """Step 1 only: natural language -> structured query (nothing is executed)."""
    return interpret(body.text, state["schema"], has_location=body.location is not None).model_dump()


@app.post("/api/execute")
def execute(query: GISQuery):
    """Step 2 only: run a structured query and return GeoJSON."""
    if query.requires_clarification:
        raise HTTPException(status_code=400, detail=query.clarification_message or "Query needs clarification")
    try:
        return run_query(query, state["schema"])
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except psycopg2.Error as err:
        raise HTTPException(status_code=500, detail=f"Database error: {err}")


@app.post("/api/ask")
def ask(body: AskRequest):
    print(f"\n>>> [INCOMING REQUEST] /api/ask: {body.text}", flush=True)
    """Full pipeline used by the web page: interpret, then execute."""
    query = interpret(body.text, state["schema"], has_location=body.location is not None)
    interpreted = query.model_dump()

    if query.requires_clarification:
        return {"interpreted": interpreted, "clarification": query.clarification_message}

    try:
        result = run_query(query, state["schema"],location=body.location)
    except ValueError as err:
        return {"interpreted": interpreted, "clarification": f"I couldn't build that query: {err}"}
    except psycopg2.Error as err:
        return {"interpreted": interpreted, "clarification": f"The database rejected the query: {err}"}

    # Add notice if dataset was capped or large
    response_payload = {"interpreted": interpreted, **result}
    if result["total"] > result["returned"]:
        response_payload["notice"] = (
            f"Showing first {result['returned']} of {result['total']} matching features."
        )

    return response_payload
