from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from dotenv import dotenv_values
from typing import List, Dict, Any
from pathlib import Path

# Cargar .env desde ruta relativa al archivo
BASE_DIR = Path(__file__).resolve().parent
config = dotenv_values(BASE_DIR.parent.parent / ".env")

user = config.get("DB_USER_LLM")
pwd  = quote_plus(config.get("DB_PASSWORD_LLM") or "")  # URL-encode
host = config.get("DB_HOST_LLM", "localhost")
db   = config.get("DB_NAME_LLM")

DSN = f"postgresql+psycopg://{user}:{pwd}@{host}/{db}"

# Crea el engine con psycopg3
engine = create_engine(DSN, pool_pre_ping=True)

def run_query_secure(sql: str, limit_default: int = 500) -> List[Dict[str, Any]]:
    """
    Ejecuta SELECT/WITH/EXPLAIN con timeouts y search_path controlado.
    Fuerza LIMIT si no viene especificado.
    """
    # Forzar LIMIT si no aparece en la sentencia
    sql_limited = sql if "limit" in sql.lower() else f"{sql.rstrip(';')} LIMIT {limit_default};"
    with engine.begin() as conn:
        # Timeouts y search_path seguros por sesión
        conn.exec_driver_sql("SET statement_timeout TO '15s';")
        conn.exec_driver_sql("SET idle_in_transaction_session_timeout TO '10s';")
        # Ajusta los esquemas a tu realidad:
        conn.exec_driver_sql(
            "SET search_path TO datos_crudos, datos_maestros, medio_fisico, specimen, public;"
        )
        result = conn.execute(text(sql_limited))
        rows = [dict(row) for row in result.mappings()]
    return rows

def ping_version() -> str:
    """Devuelve la versión de PostgreSQL para verificar conectividad básica."""
    with engine.begin() as conn:
        conn.exec_driver_sql("SET statement_timeout TO '5s';")
        v = conn.execute(text("SELECT version() AS ver")).scalar()
    return str(v)
