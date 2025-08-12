# db/schema_cache.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text
from db.engine import engine

PREFERRED_GEOM_ORDER = ("geometria", "geometry", "geom", "the_geom")

@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool
    is_pk: bool = False

@dataclass
class GeometryInfo:
    column: str
    srid: Optional[int]
    gtype: Optional[str]  # POINT/POLYGON/…

@dataclass
class IndexInfo:
    name: str
    method: str  # gist/brin/btree
    columns: List[str]

@dataclass
class TableInfo:
    schema: str
    table: str
    columns: List[ColumnInfo]
    pk_cols: List[str]
    geom: Optional[GeometryInfo]
    indexes: List[IndexInfo]
    fks: List[Tuple[List[str], str, List[str]]]  # (local_cols, ref_table, ref_cols)

_cache: Dict[Tuple[str, str], TableInfo] = {}
_loaded = False

def _fetch_rows(sql: str, **params):
    with engine.begin() as conn:
        return list(conn.execute(text(sql), params))

def _load_columns(schema: str, table: str) -> List[ColumnInfo]:
    rows = _fetch_rows("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema=:s AND table_name=:t
        ORDER BY ordinal_position
    """, s=schema, t=table)
    return [ColumnInfo(r[0], r[1], r[2] == "YES") for r in rows]

def _load_pk(schema: str, table: str) -> List[str]:
    rows = _fetch_rows("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_class c ON c.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum = ANY(i.indkey)
        WHERE n.nspname=:s AND c.relname=:t AND i.indisprimary
        ORDER BY a.attnum
    """, s=schema, t=table)
    return [r[0] for r in rows]

def _load_indexes(schema: str, table: str) -> List[IndexInfo]:
    rows = _fetch_rows("""
        SELECT i.relname AS index_name,
               am.amname  AS method,
               array_agg(a.attname ORDER BY a.attnum) AS cols
        FROM pg_index idx
        JOIN pg_class t ON t.oid=idx.indrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class i ON i.oid=idx.indexrelid
        JOIN pg_am am ON am.oid=i.relam
        JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum = ANY(idx.indkey)
        WHERE n.nspname=:s AND t.relname=:t
        GROUP BY i.relname, am.amname
    """, s=schema, t=table)
    return [IndexInfo(r[0], r[1], list(r[2])) for r in rows]

def _load_fks(schema: str, table: str) -> List[Tuple[List[str], str, List[str]]]:
    rows = _fetch_rows("""
        SELECT
          array_agg(la.attname ORDER BY la.attnum) AS local_cols,
          rn.nspname || '.' || rt.relname AS ref_table,
          array_agg(ra.attname ORDER BY ra.attnum) AS ref_cols
        FROM pg_constraint c
        JOIN pg_class lt ON lt.oid = c.conrelid
        JOIN pg_namespace ln ON ln.oid = lt.relnamespace
        JOIN pg_class rt ON rt.oid = c.confrelid
        JOIN pg_namespace rn ON rn.oid = rt.relnamespace
        JOIN unnest(c.conkey) WITH ORDINALITY AS l(attnum, ord) ON TRUE
        JOIN unnest(c.confkey) WITH ORDINALITY AS r(attnum, ord) ON r.ord = l.ord
        JOIN pg_attribute la ON la.attrelid = lt.oid AND la.attnum = l.attnum
        JOIN pg_attribute ra ON ra.attrelid = rt.oid AND ra.attnum = r.attnum
        WHERE c.contype='f' AND ln.nspname=:s AND lt.relname=:t
        GROUP BY rn.nspname, rt.relname
    """, s=schema, t=table)
    return [(list(r[0]), r[1], list(r[2])) for r in rows]

def _load_geometry(schema: str, table: str) -> Optional[GeometryInfo]:
    # geometry_columns (siempre que esté poblada)
    rows = _fetch_rows("""
        SELECT f_geometry_column, srid, type
        FROM public.geometry_columns
        WHERE f_table_schema=:s AND f_table_name=:t
    """, s=schema, t=table)
    if rows:
        best = sorted(
            rows,
            key=lambda r: PREFERRED_GEOM_ORDER.index(r[0])
            if r[0] in PREFERRED_GEOM_ORDER else len(PREFERRED_GEOM_ORDER)
        )[0]
        return GeometryInfo(best[0], best[1], best[2])

    # Fallback por nombre conocido si geometry_columns no está poblada
    cols = _load_columns(schema, table)
    candidates = [c.name for c in cols if c.name.lower() in PREFERRED_GEOM_ORDER]
    if candidates:
        c0 = sorted(candidates, key=lambda n: PREFERRED_GEOM_ORDER.index(n))[0]
        return GeometryInfo(c0, None, None)
    return None

def load_schema_cache(allowed_schemas: List[str]) -> None:
    global _cache, _loaded
    _cache.clear()
    tables = _fetch_rows("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type='BASE TABLE' AND table_schema = ANY(:schemas)
    """, schemas=allowed_schemas)
    for s, t in tables:
        cols = _load_columns(s, t)
        pk = set(_load_pk(s, t))
        for c in cols:
            if c.name in pk:
                c.is_pk = True
        geom = _load_geometry(s, t)
        idxs = _load_indexes(s, t)
        fks = _load_fks(s, t)
        _cache[(s, t)] = TableInfo(
            schema=s, table=t, columns=cols, pk_cols=list(pk),
            geom=geom, indexes=idxs, fks=fks
        )
    _loaded = True

def get_table(schema: str, table: str) -> Optional[TableInfo]:
    return _cache.get((schema, table))

def best_geom_column(ti: TableInfo) -> Optional[str]:
    if ti.geom:
        return ti.geom.column
    names = [c.name for c in ti.columns]
    for pref in PREFERRED_GEOM_ORDER:
        if pref in names:
            return pref
    return None

def to_ctx_line(ti: TableInfo) -> str:
    cols_txt = ", ".join(
        f"{c.name}:{c.data_type}{' PK' if c.is_pk else ''}"
        for c in ti.columns
    )
    geom_txt = "geom: desconocido"
    if ti.geom:
        geom_txt = f"geom={ti.geom.column} srid={ti.geom.srid or 'unk'} type={ti.geom.gtype or 'unk'}"
    idx_gist = [i for i in ti.indexes if i.method in ("gist","brin")]
    idx_txt = "; ".join([f"{i.method}:{','.join(i.columns)}" for i in idx_gist]) or "no_spatial_index"
    return f"- {ti.schema}.{ti.table}: [{cols_txt}] | {geom_txt} | idx({idx_txt})"

def suggest_id_column(ti: TableInfo) -> Optional[str]:
    if ti.pk_cols:
        return ti.pk_cols[0]
    for name in ("objectid","gid","id","pk","codigo","cod","cod_id"):
        for c in ti.columns:
            if c.name.lower() == name:
                return c.name
    ints = [c.name for c in ti.columns if ("int" in c.data_type and not c.is_nullable)]
    return ints[0] if ints else None

def preferred_geom(ti: TableInfo) -> Optional[str]:
    return best_geom_column(ti)
