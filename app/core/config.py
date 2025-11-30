from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8081
    DEBUG: bool = True

    # WebSocket settings
    WS_MAX_SIZE: int = 2 ** 20  # 1MB
    WS_TIMEOUT: int = 30

    # Audio settings
    SAMPLE_RATE: int = 16000
    CHUNK_SIZE: int = 1024

    # ML settings
    MODEL_PATH: str = "models/stt_model"
    PUNCTUATION_MODEL_PATH: str = "models/punctuation_model"

    class Config:
        env_file = ".env"


settings = Settings()