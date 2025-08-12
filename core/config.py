# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # Directorio base donde guardas los modelos
    MODELS_DIR: str = "llm/models"

    # Ruta relativa (desde MODELS_DIR) a tu GGUF de SQLCoder
    # Usa exactamente el nombre/carpeta que ya tienes
    MODEL_SQL_PATH: str = "sqlcoder-7b-2/sqlcoder-7b-q5_k_m.gguf"

    # Ollama (Llama3) para explicaciones/chat
    OLLAMA_HOST: str = "http://127.0.0.1:11434"
    OLLAMA_CHAT_MODEL: str = "llama3"

    # Pydantic settings
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Ruta absoluta/normalizada al archivo GGUF de SQLCoder
    @property
    def SQL_MODEL_FILE(self) -> str:
        return str((Path(self.MODELS_DIR) / self.MODEL_SQL_PATH).resolve())

settings = Settings()
