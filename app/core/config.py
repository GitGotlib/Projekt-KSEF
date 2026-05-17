from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ksef_db"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    APP_ENV: str = "development"
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
