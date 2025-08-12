# db/introspect.py
from __future__ import annotations
import re
from typing import List, Tuple, Dict, Any, Optional

# Dependencias del caché/catálogo
from db.schema_cache import (
    get_table,            # -> retorna metadata de la tabla
    suggest_id_column,    # -> sugiere PK real
    preferred_geom,       # -> sugiere columna geom (geometria/geometry/geom/etc.)
)

# ---- Detectar referencias a tablas en texto ---------------------------------

# 1) Forma "schema.tabla"
DOT_REF_RE = re.compile(r"\b([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\b")

# 2) Frases tipo: "del esquema datos_maestros ... tabla dpa_region_subdere"
PHRASE_REF_RE = re.compile(
    r"(?:\besquema\b|\bschema\b)\s+([a-zA-Z0-9_]+).*?(?:\btabla\b|\btable\b)\s+([a-zA-Z0-9_]+)",
    re.IGNORECASE | re.DOTALL,
)

def find_table_refs(text: str) -> List[Tuple[str, str]]:
    """
    Extrae pares (schema, table) tanto en forma 'schema.tabla' como en frases:
    '... del esquema X ... tabla Y ...'.
    """
    refs: List[Tuple[str, str]] = []
    if not text:
        return refs

    # a) 'schema.table'
    for s, t in DOT_REF_RE.findall(text):
        refs.append((s, t))

    # b) 'esquema X ... tabla Y'
    for s, t in PHRASE_REF_RE.findall(text):
        refs.append((s, t))

    # quitar duplicados preservando orden
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for st in refs:
        if st not in seen:
            uniq.append(st)
            seen.add(st)
    return uniq


# ---- Construir contexto de esquema para el prompt ---------------------------

def _columns_preview(ti: Any) -> str:
    """
    Intenta renderizar una lista corta de columnas desde la metadata de la tabla.
    Soporta dict/list/tuplas/objetos con atributo 'name'.
    """
    cols = getattr(ti, "columns", None)
    names: List[str] = []
    if isinstance(cols, dict):
        names = list(cols.keys())
    elif isinstance(cols, (list, tuple)):
        for c in cols:
            if isinstance(c, str):
                names.append(c)
            elif hasattr(c, "name"):
                names.append(str(getattr(c, "name")))
            elif isinstance(c, (list, tuple)) and c:
                names.append(str(c[0]))
            else:
                names.append(str(c))
    # corta para no hacer prompts gigantes
    if not names:
        return ""
    return ", ".join(names[:30])

def build_schema_ctx(question_or_sql: str, extra_metadata: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """
    Construye líneas compactas por cada (schema.table) detectado:
      <schema>.<table> (cols: col1, col2, ...) | pk=<...> | geom=<...> | srid=<...>

    - Usa find_table_refs() para detectar tablas en la pregunta/SQL.
    - Obtiene PK/geom/SRID reales del catálogo (db.schema_cache).
    - Permite sobreescrituras vía extra_metadata (opcional).
    """
    refs = find_table_refs(question_or_sql or "")
    if not refs:
        return ""

    lines: List[str] = []
    extra_metadata = extra_metadata or {}

    for schema, table in refs:
        ti = get_table(schema, table)
        if not ti:
            # Si no encontramos metadata, al menos listamos el nombre
            lines.append(f"{schema}.{table} | pk=unk | geom=unk | srid=unk")
            continue

        # columnas (si están disponibles)
        cols_preview = _columns_preview(ti)
        cols_txt = f"(cols: {cols_preview}) " if cols_preview else ""

        # hints base desde catálogo
        pk_hint = suggest_id_column(ti)
        geom_hint = preferred_geom(ti)
        srid_val = getattr(getattr(ti, "geom", None), "srid", None)

        # overrides desde extra_metadata si vienen
        key = f"{schema}.{table}"
        if key in extra_metadata:
            md = extra_metadata[key]
            pk_hint = md.get("pk", pk_hint)
            geom_hint = md.get("geom_col", md.get("geom", geom_hint))
            srid_val = md.get("srid", srid_val)

        srid_txt = str(srid_val) if srid_val is not None else "unk"
        pk_txt = pk_hint or "unk"
        geom_txt = geom_hint or "unk"

        line = f"{schema}.{table} {cols_txt}| pk={pk_txt} | geom={geom_txt} | srid={srid_txt}"
        lines.append(line)

    # limitar tamaño total del contexto
    ctx = "\n".join(lines)
    return ctx[:5000]
