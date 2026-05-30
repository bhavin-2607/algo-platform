from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT:   str = "development"
    SECRET_KEY:    str = "change-me-in-production"
    JWT_SECRET:    str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ENCRYPTION_KEY:str = "change-me-32-bytes-key-here!!!!"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 1440   # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS:    int = 30

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://algo_user:password@localhost/algo_platform"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Dhan (primary broker) ─────────────────────────────────────────────────
    DHAN_PIN:         str = ""
    DHAN_TOTP_SECRET: str = ""
    SMTP_HOST:        str = ""   # optional email alerts
    SMTP_PORT:        int = 587
    ALERT_EMAIL:      str = ""
    DHAN_CLIENT_ID:    str = ""
    DHAN_ACCESS_TOKEN: str = ""

    # ── Shoonya (legacy — optional, not shown in UI) ──────────────────────────
    SHOONYA_USER_ID:     str = ""
    SHOONYA_PASSWORD:    str = ""
    SHOONYA_TOTP_SECRET: str = ""
    SHOONYA_VENDOR_CODE: str = ""
    SHOONYA_API_SECRET:  str = ""
    SHOONYA_IMEI:        str = "algo-platform-v1"

    class Config:
        env_file = ".env"
        extra    = "ignore"


settings = Settings()
