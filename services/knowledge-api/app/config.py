from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql://sediment:sediment@localhost:5432/sediment"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_synthesis_model: str = "gemini-2.5-flash"
    db_pool_min: int = 1
    db_pool_max: int = 5
    default_top_k: int = 10
    default_min_score: float = 0.5


settings = Settings()
