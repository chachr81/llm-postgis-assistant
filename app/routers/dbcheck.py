from fastapi import APIRouter
from db.engine import ping_version, run_query_secure

router = APIRouter()

@router.get("/db/ping")
def db_ping():
    return {"ok": True, "version": ping_version()}

@router.get("/db/sample")
def db_sample():
    # Ajusta a una tabla visible por llm_read, aquí listamos tablas de usuario
    rows = run_query_secure("SELECT schemaname, relname FROM pg_catalog.pg_stat_user_tables")
    return {"count": len(rows), "rows": rows[:20]}
