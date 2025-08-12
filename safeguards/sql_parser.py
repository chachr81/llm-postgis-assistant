# safeguards/sql_parser.py
import sqlglot
from sqlglot.expressions import Select, With

# Permitimos solo SELECT/WITH (y EXPLAIN de esos mismos)
ALLOW = (Select, With)

BLOCK_KW = (
    " drop ", " truncate ", " alter ", " delete ", " update ", " insert ",
    " create table ", " create schema ", " create index ", " grant ", " revoke ",
    " vacuum ", " analyze ", " copy ", " call ", " do "
)

def is_safe_sql(sql: str) -> tuple[bool, str]:
    """
    Valida que la sentencia sea SELECT/WITH o EXPLAIN de una de esas.
    Usa sqlglot para parsear el AST sin depender de la clase Explain (que no siempre existe).
    """
    if not sql or not sql.strip():
        return False, "SQL vacío"

    s = sql.strip().rstrip(";")
    low = s.lower().lstrip()

    # Si empieza con EXPLAIN, parseamos la parte de detrás para validar que sea SELECT/WITH
    if low.startswith("explain "):
        # quita el prefijo "explain" y flags opcionales simples
        # (manejo básico: si hay EXPLAIN (FORMAT JSON) lo dejamos; solo validamos que la consulta base sea SELECT/WITH)
        try:
            # Intenta encontrar el primer "select"/"with" en el string para parsear desde ahí
            idx_sel = low.find(" select ")
            idx_with = low.find(" with ")
            idx = max(idx_sel, idx_with)
            if idx == -1:
                # fallback: quitar solo la palabra explain y parsear el resto
                inner = s.split(None, 1)[1]
            else:
                inner = s[idx:].lstrip()
            ast = sqlglot.parse_one(inner, read="postgres")
        except Exception as e:
            return False, f"Parse error (EXPLAIN): {e}"

        if not isinstance(ast, ALLOW):
            return False, "EXPLAIN solo permitido sobre SELECT/WITH"
        # blocklist igualmente
        low_padded = f" {s.lower()} "
        for kw in BLOCK_KW:
            if kw in low_padded:
                return False, f"Keyword bloqueada: {kw.strip().upper()}"
        return True, "OK"

    # Caso normal: SELECT/WITH
    try:
        ast = sqlglot.parse_one(s, read="postgres")
    except Exception as e:
        return False, f"Parse error: {e}"

    if not isinstance(ast, ALLOW):
        # Mensaje claro con la clave del nodo
        node = getattr(ast, "key", "").upper() or type(ast).__name__
        return False, f"Solo SELECT/WITH/EXPLAIN permitidos (recibido: {node})"

    low_padded = f" {low} "
    for kw in BLOCK_KW:
        if kw in low_padded:
            return False, f"Keyword bloqueada: {kw.strip().upper()}"

    return True, "OK"