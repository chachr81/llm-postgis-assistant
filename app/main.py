"""Main entry point for the LLM PostGIS Assistant FastAPI application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers import dbcheck, chat
from db.schema_cache import load_schema_cache

ALLOWED_SCHEMAS = ["public", "datos_crudos", "datos_maestros", "medio_fisico", "specimen"]

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Lifespan event handler to load the schema cache at startup."""
    load_schema_cache(ALLOWED_SCHEMAS)
    yield

app = FastAPI(title="LLM PostGIS Assistant", lifespan=lifespan)

app.include_router(dbcheck.router, prefix="/api")
app.include_router(chat.router,   prefix="/api")