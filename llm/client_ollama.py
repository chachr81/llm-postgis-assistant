# llm/client_ollama.py
import os, requests
from core.config import settings

# Permite override por variable de entorno o usa lo del config.py
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", settings.OLLAMA_HOST)
CHAT_MODEL  = os.environ.get("OLLAMA_CHAT_MODEL", settings.OLLAMA_CHAT_MODEL)

def _gen(model: str, prompt: str, **kw):
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    payload.update(kw)
    r = requests.post(url, json=payload, timeout=600)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "").strip()

def infer_chat(prompt: str) -> str:
    # respuesta breve en español
    return _gen(CHAT_MODEL, prompt, options={"temperature": 0.4, "num_predict": 300})
