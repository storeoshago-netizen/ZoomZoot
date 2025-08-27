from typing import Optional
from pydantic_settings import BaseSettings
import os


class Settings(BaseSettings):
    DATABASE_URL: str
    AZURE_OPENAI_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-35-turbo"
    ALLOWED_ORIGINS: str = "http://localhost:8000"
    AI_PROVIDER: str = "azure_openai"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    aviasales_api_key: Optional[str] = None
    travelpayouts_api_key: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
