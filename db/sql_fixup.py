# db/sql_fixup.py
import re
from typing import Dict, List, Tuple, Optional, Set
from db.introspect import find_table_refs
from db.schema_cache import get_table as cache_get_table, suggest_id_column, preferred_geom

# SRID proyectado para unidades métricas/hectáreas
METRIC_SRID = 32719  # EPSG:32719 (UTM 19S)

# Regex para capturar alias en FROM/JOIN
ALIAS_FROM_RE = re.compile(
    r"\bfrom\s+([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s+(?:as\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)
ALIAS_JOIN_RE = re.compile(
    r"\bjoin\s+([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s+(?:as\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)

# schema.table.col
QUAL_COL_RE = re.compile(
    r"\b([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\.([a-zA-Z_][a-zA-Z0-9_]*)\b"
)
# table.col (sin schema)
TBL_COL_RE = re.compile(
    r"\b([a-zA-Z0-9_]+)\.([a-zA-Z_][a-zA-Z0-9_]*)\b"
)

def _collect_aliases(sql: str) -> Dict[str, Tuple[str, str]]:
    alias_map: Dict[str, Tuple[str, str]] = {}
    for m in ALIAS_FROM_RE.finditer(sql):
        alias_map[m.group(3)] = (m.group(1), m.group(2))
    for m in ALIAS_JOIN_RE.finditer(sql):
        alias_map[m.group(3)] = (m.group(1), m.group(2))
    return alias_map

def _srid_for(schema: str, table: str) -> Optional[int]:
    ti = cache_get_table(schema, table)
    return ti.geom.srid if ti and ti.geom else None

def _geom_for(schema: str, table: str) -> Optional[str]:
    ti = cache_get_table(schema, table)
    return preferred_geom(ti) if ti else None

def _id_for(schema: str, table: str) -> Optional[str]:
    ti = cache_get_table(schema, table)
    return suggest_id_column(ti) if ti else None

def _mentions_metric_units(text: str) -> bool:
    q = (text or "").lower()
    return any(w in q for w in (" metro", " metros", " m ", " km", "kilometro", "kilómetro", "kilometros", "kilómetros"))

def _mentions_hectares(text: str) -> bool:
    q = (text or "").lower()
    return any(w in q for w in ("hectarea", "hectárea", "hectareas", "hectáreas", " ha", " en ha", " en hectá"))

def _build_table_meta(question: str, sql: str) -> Tuple[
    Dict[Tuple[str, str], Dict[str, Optional[str]]],  # meta por (schema, table)
    Dict[str, Tuple[str, str]],                       # nombre_de_tabla_simple -> (schema, table) si no ambiguo
]:
    """
    Usa find_table_refs sobre pregunta y SQL para construir:
    - meta[(schema, table)] = { 'id':.., 'geom':.., 'srid':.. }
    - simple_map['table'] = (schema, table) sólo si el nombre de tabla no es ambiguo
    """
    refs: Set[Tuple[str, str]] = set()
    for s, t in find_table_refs(question or ""):
        refs.add((s, t))
    for s, t in find_table_refs(sql or ""):
        refs.add((s, t))

    meta: Dict[Tuple[str, str], Dict[str, Optional[str]]] = {}
    # Para detectar ambigüedad de nombres sin schema
    names_count: Dict[str, int] = {}
    for s, t in refs:
        names_count[t] = names_count.get(t, 0) + 1

    simple_map: Dict[str, Tuple[str, str]] = {}
    for s, t in refs:
        ti = cache_get_table(s, t)
        if not ti:
            continue
        meta[(s, t)] = {
            "id": _id_for(s, t),
            "geom": _geom_for(s, t),
            "srid": str(_srid_for(s, t) or "")
        }
        if names_count.get(t, 0) == 1:
            simple_map[t] = (s, t)

    return meta, simple_map

def fix_sql(sql: str, question: str) -> Tuple[str, List[str]]:
    """
    Arregla automáticamente:
    - alias.id / alias.geom -> columnas reales según catálogo
    - schema.table.id / schema.table.geom -> idem
    - table.id / table.geom (sin schema) -> idem si el nombre no es ambiguo
    - ST_DWithin / ST_Intersects: armoniza SRID; si pides metros/km -> normaliza a EPSG:32719
    - ST_Area(...): si pides hectáreas -> transforma a EPSG:32719 y divide entre 10000
    """
    fixes: List[str] = []
    out = sql

    # 0) Metadatos por tablas (desde pregunta y/sql)
    table_meta, simple_map = _build_table_meta(question, out)

    # 1) Alias map
    alias_map = _collect_aliases(out)

    # 2) Sustitución por alias (a.id / a.geom)
    for alias, (sch, tab) in alias_map.items():
        id_hint = table_meta.get((sch, tab), {}).get("id") or _id_for(sch, tab)
        geom_hint = table_meta.get((sch, tab), {}).get("geom") or _geom_for(sch, tab)

        if id_hint and re.search(rf"\b{alias}\.id\b", out):
            out = re.sub(rf"\b({alias})\.id\b", rf"\1.{id_hint}", out)
            fixes.append(f"{alias}.id -> {alias}.{id_hint}")

        if geom_hint and re.search(rf"\b{alias}\.(geom|geometry|geometria)\b", out, flags=re.IGNORECASE):
            out = re.sub(rf"\b({alias})\.(geom|geometry|geometria)\b", rf"\1.{geom_hint}", out, flags=re.IGNORECASE)
            fixes.append(f"{alias}.geom -> {alias}.{geom_hint}")

    # 3) Sustitución por referencia totalmente calificada schema.table.id / .geom
    #    (esto cubre SQL que no usa alias en algunas expresiones)
    for (sch, tab), meta in table_meta.items():
        id_hint = meta.get("id")
        geom_hint = meta.get("geom")
        if id_hint:
            pattern = re.compile(rf"\b{re.escape(sch)}\.{re.escape(tab)}\.id\b")
            if pattern.search(out):
                out = pattern.sub(f"{sch}.{tab}.{id_hint}", out)
                fixes.append(f"{sch}.{tab}.id -> {sch}.{tab}.{id_hint}")
        if geom_hint:
            pattern = re.compile(rf"\b{re.escape(sch)}\.{re.escape(tab)}\.(geom|geometry|geometria)\b", re.IGNORECASE)
            if pattern.search(out):
                out = pattern.sub(f"{sch}.{tab}.{geom_hint}", out)
                fixes.append(f"{sch}.{tab}.geom -> {sch}.{tab}.{geom_hint}")

    # 4) Sustitución por nombre de tabla sin schema (sólo si no ambiguo)
    for tbl, (sch, tab) in simple_map.items():
        meta = table_meta.get((sch, tab), {})
        id_hint = meta.get("id")
        geom_hint = meta.get("geom")
        if id_hint:
            pattern = re.compile(rf"\b{re.escape(tbl)}\.id\b")
            if pattern.search(out):
                out = pattern.sub(f"{tbl}.{id_hint}", out)
                fixes.append(f"{tbl}.id -> {tbl}.{id_hint}")
        if geom_hint:
            pattern = re.compile(rf"\b{re.escape(tbl)}\.(geom|geometry|geometria)\b", re.IGNORECASE)
            if pattern.search(out):
                out = pattern.sub(f"{tbl}.{geom_hint}", out)
                fixes.append(f"{tbl}.geom -> {tbl}.{geom_hint}")

    # 5) Unidades solicitadas
    want_metric = _mentions_metric_units(question)
    want_hectares = _mentions_hectares(question)

    # 6) Identificar alias de la primera tabla en FROM (intento de tabla 'grande')
    first_from_alias = None
    mfirst = ALIAS_FROM_RE.search(out)
    if mfirst:
        first_from_alias = mfirst.group(3)

    def _wrap_transform(alias: str, col: str, target_srid: Optional[int]) -> str:
        if not target_srid:
            return f"{alias}.{col}"
        return f"ST_Transform({alias}.{col},{target_srid})"

    # Resolver expr → (schema, table, alias, column)
    def _resolve_expr(expr: str) -> Optional[Tuple[str, str, Optional[str], str]]:
        expr = expr.strip()
        # alias.col
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)$", expr)
        if m:
            alias, col = m.group(1), m.group(2)
            if alias in alias_map:
                s, t = alias_map[alias]
                return (s, t, alias, col)
            # si alias no está en alias_map, intentar como table.col (sin schema) si no ambiguo
            if alias in simple_map:
                s, t = simple_map[alias]
                return (s, t, None, col)
            return None
        # schema.table.col
        m = QUAL_COL_RE.match(expr)
        if m:
            s, t, col = m.group(1), m.group(2), m.group(3)
            return (s, t, None, col)
        return None

    # 7) Normalizar SRID en ST_DWithin / ST_Intersects
    def _fix_st_geom_pair(match: re.Match) -> str:
        func = match.group(1)
        arg1 = match.group(2).strip()
        arg2 = match.group(3).strip()
        rest = match.group(4) or ""

        # respetar si ya hay ST_Transform explícito
        if re.search(r"ST_Transform\s*\(", arg1, re.IGNORECASE) or re.search(r"ST_Transform\s*\(", arg2, re.IGNORECASE):
            return match.group(0)

        r1 = _resolve_expr(arg1)
        r2 = _resolve_expr(arg2)
        if not r1 or not r2:
            return match.group(0)

        s1, t1, a1, c1 = r1
        s2, t2, a2, c2 = r2
        srid1 = int(table_meta.get((s1, t1), {}).get("srid") or 0) or _srid_for(s1, t1)
        srid2 = int(table_meta.get((s2, t2), {}).get("srid") or 0) or _srid_for(s2, t2)

        if want_metric:
            target = METRIC_SRID
            # no transformes la tabla grande (first_from_alias) si aplica
            tx1 = None if (a1 and a1 == first_from_alias) else (target if srid1 != target else None)
            tx2 = None if (a2 and a2 == first_from_alias) else (target if srid2 != target else None)
            new1 = _wrap_transform(a1 or f"{s1}.{t1}", c1, tx1) if a1 else (f"ST_Transform({s1}.{t1}.{c1},{target})" if tx1 else f"{s1}.{t1}.{c1}")
            new2 = _wrap_transform(a2 or f"{s2}.{t2}", c2, tx2) if a2 else (f"ST_Transform({s2}.{t2}.{c2},{target})" if tx2 else f"{s2}.{t2}.{c2}")
            fixes.append(f"{func}: normalizado a EPSG:{target} (metros/km)")
            return f"{func}({new1}, {new2}{rest})"

        # Si no pides metros: unificar al SRID del lado 'grande' (primer FROM)
        if srid1 and srid2 and srid1 != srid2:
            if a1 and a1 == first_from_alias:
                new1 = f"{a1}.{c1}"
                new2 = _wrap_transform(a2 or f"{s2}.{t2}", c2, srid1) if a2 else f"ST_Transform({s2}.{t2}.{c2},{srid1})"
            elif a2 and a2 == first_from_alias:
                new1 = _wrap_transform(a1 or f"{s1}.{t1}", c1, srid2) if a1 else f"ST_Transform({s1}.{t1}.{c1},{srid2})"
                new2 = f"{a2}.{c2}"
            else:
                # por consistencia, transformar arg2 al srid de arg1
                new1 = f"{a1}.{c1}" if a1 else f"{s1}.{t1}.{c1}"
                new2 = _wrap_transform(a2 or f"{s2}.{t2}", c2, srid1) if a2 else f"ST_Transform({s2}.{t2}.{c2},{srid1})"
            fixes.append(f"{func}: unificados SRIDs por consistencia")
            return f"{func}({new1}, {new2}{rest})"

        return match.group(0)

    out = re.sub(
        r"\b(ST_DWithin|ST_Intersects)\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*(,\s*[^)]+)?\)",
        _fix_st_geom_pair,
        out,
        flags=re.IGNORECASE,
    )

    # 8) Áreas → hectáreas (ST_Area(...)/10000)
    if want_hectares:
        def _fix_area(ma: re.Match) -> str:
            inner = ma.group(1).strip()
            if re.search(r"ST_Transform\s*\(", inner, re.IGNORECASE):
                # ya transformado: solo divide
                return f"({ma.group(0)})/10000.0"
            r = _resolve_expr(inner)
            if not r:
                return f"({ma.group(0)})/10000.0"
            s, t, a, c = r
            if a and a == first_from_alias:
                # no toques la 'grande'
                expr = f"{a}.{c}"
            else:
                # transforma al SRID métrico
                expr = f"ST_Transform({(a + '.' + c) if a else f'{s}.{t}.{c}'},{METRIC_SRID})"
            fixes.append(f"ST_Area: convertido a hectáreas en EPSG:{METRIC_SRID}")
            return f"ST_Area({expr})/10000.0"

        out = re.sub(r"\bST_Area\s*\(\s*([^)]+)\s*\)", _fix_area, out, flags=re.IGNORECASE)

    return out, fixes
