"""Central configuration, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "ollama"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b-instruct"

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    app_port: int = 8000
    db_dir: str = "./data/db"
    upload_dir: str = "./data/uploads"
    max_job_workers: int = 4
    query_timeout_seconds: int = 20
    llm_timeout_seconds: int = 300
    max_upload_mb: int = 200
    max_result_rows: int = 500


settings = Settings()
