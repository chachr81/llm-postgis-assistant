# llm/client_llamacpp.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
from llama_cpp import Llama
from core.config import settings

# Instancias singleton
_llm_sql: Optional[Llama] = None
_llm_chat_local: Optional[Llama] = None

def get_llm_sql() -> Llama:
    """Devuelve el modelo local (GGUF) para generación de SQL: SQLCoder."""
    global _llm_sql
    if _llm_sql is None:
        model_path = getattr(settings, "SQL_MODEL_FILE", None) or getattr(settings, "MODEL_SQL_PATH", None)
        if not model_path:
            raise RuntimeError("No se encontró la ruta del modelo SQL (SQL_MODEL_FILE / MODEL_SQL_PATH).")
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Modelo SQL no encontrado: {model_path}")
        _llm_sql = Llama(
            model_path=model_path,
            n_ctx=8192,
            n_threads=8,   # ajusta a tus CPUs
            verbose=False,
        )
    return _llm_sql

def get_llm_chat() -> Optional[Llama]:
    """
    Devuelve un modelo local de chat SÓLO si MODEL_CHAT_PATH está definido y existe.
    Si no, devolvemos None y 'infer_chat' delegará en Ollama (sin romper interfaz).
    """
    global _llm_chat_local
    if _llm_chat_local is not None:
        return _llm_chat_local

    model_chat_path = getattr(settings, "MODEL_CHAT_PATH", "") or ""
    if model_chat_path:
        if Path(model_chat_path).exists():
            _llm_chat_local = Llama(
                model_path=model_chat_path,
                n_ctx=4096,
                n_threads=8,
                verbose=False,
            )
            return _llm_chat_local
    # No hay modelo local de chat → se usará Ollama en infer_chat()
    return None

def infer_sql(prompt: str) -> str:
    out = get_llm_sql()(prompt=prompt, max_tokens=512, temperature=0.1, stop=["```"])
    return out["choices"][0]["text"].strip()

def infer_chat(prompt: str) -> str:
    """
    Mantiene la firma original. Si hay modelo local de chat (MODEL_CHAT_PATH), lo usa.
    Si no, delega a Ollama (Llama3) a través del cliente HTTP.
    """
    llm = get_llm_chat()
    if llm is not None:
        out = llm(prompt=prompt, max_tokens=512, temperature=0.3)
        return out["choices"][0]["text"].strip()

    # Fallback automático: Ollama (sin cambiar imports en el resto del código)
    try:
        from llm.client_ollama import infer_chat as _ollama_chat
    except Exception as e:
        raise RuntimeError(
            "No hay modelo local de chat (MODEL_CHAT_PATH vacío/inválido) "
            "y no se pudo importar el cliente de Ollama. "
            "Instala/activa Ollama o define MODEL_CHAT_PATH."
        ) from e
    return _ollama_chat(prompt)
