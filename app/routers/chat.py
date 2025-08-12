# app/routers/chat.py
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from safeguards.sql_parser import is_safe_sql
from db.explain_gate import explain_summary, too_expensive
from db.engine import run_query_secure
from db.introspect import build_schema_ctx, find_table_refs
from db.sql_fixup import fix_sql

from llm.prompts import build_sql_prompt
from llm.client_llamacpp import infer_sql, infer_chat

router = APIRouter()

class ChatIn(BaseModel):
    question: Optional[str] = None
    sql: Optional[str] = None
    execute: bool = True

@router.post("/chat")
def chat(in_: ChatIn):
    if not in_.sql and not in_.question:
        raise HTTPException(status_code=400, detail="Proporciona 'sql' o 'question'.")

    user_text = in_.question if in_.question else in_.sql
    # Detecta tablas mencionadas explícitamente
    refs = find_table_refs(user_text or "")

    # 1) NL → SQL con contexto por tablas referenciadas
    if in_.question:
        # ✅ Usamos explícitamente las refs para que build_schema_ctx las considere
        # (sin cambiar su firma): le “inyectamos” las refs al texto.
        refs_hint = ""
        if refs:
            refs_hint = "\n\nTABLAS_MENCIONADAS:\n" + "\n".join(f"{s}.{t}" for s, t in refs)

        schema_ctx = build_schema_ctx((in_.question or "") + refs_hint)
        prompt = build_sql_prompt(in_.question, schema_ctx=schema_ctx)
        sql_block = infer_sql(prompt)
        sql = (sql_block or "").strip()
        if sql.startswith("```sql"):
            sql = sql.replace("```sql", "").replace("```", "").strip()
    else:
        sql = (in_.sql or "").strip()

    if not sql:
        raise HTTPException(status_code=400, detail="No se pudo generar SQL; intenta ser más específico.")

    # 2) Validación de políticas
    ok, reason = is_safe_sql(sql)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Bloqueado: {reason}")

    # 2.1) Fix automático: id/geom + SRIDs + hectáreas (si corresponde)
    sql_fixed, fixes = fix_sql(sql, in_.question or "")
    if fixes:
        sql = sql_fixed

    # 3) EXPLAIN-gate
    plan = explain_summary(sql)
    if isinstance(plan, dict) and "error" in plan:
        return {
            "question": in_.question,
            "refs": refs,
            "sql": sql,
            "executed": False,
            "plan": plan,
            "fixes": fixes,
            "error": "EXPLAIN falló; revisa columnas/joins o el contexto de esquema.",
        }

    blocked, why = too_expensive(plan)
    if blocked:
        return {
            "question": in_.question,
            "refs": refs,
            "sql": sql,
            "executed": False,
            "plan": plan,
            "fixes": fixes,
            "error": f"Plan bloqueado por coste/tamaño: {why}",
        }

    # 4) Ejecutar (solo lectura)
    rows = run_query_secure(sql) if in_.execute else []

    # 5) Explicación breve en español (PostgreSQL/PostGIS)
    explanation_prompt = (
        "Explica en español, de forma breve y usando terminología de PostgreSQL/PostGIS, "
        f"qué hace esta consulta SQL:\n{sql}"
    )
    explanation = infer_chat(explanation_prompt)

    return {
        "question": in_.question,
        "refs": refs,
        "sql": sql,
        "executed": in_.execute,
        "plan": plan,
        "fixes": fixes,
        "rows": rows[:500],
        "explain": explanation,
    }
