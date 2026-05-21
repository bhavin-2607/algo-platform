from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "change-me"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    DATABASE_URL: str = "postgresql+asyncpg://algo_user:password@postgres:5432/algo_platform"
    REDIS_URL: str = "redis://:password@redis:6379/0"

    JWT_SECRET: str = "change-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ENCRYPTION_KEY: str = "change-this-32-byte-key-for-prod!"

    MFA_ISSUER: str = "AlgoTradingPlatform"

    # Dhan / DhanHQ credentials (simpler than Shoonya — just client_id + access_token)
    DHAN_CLIENT_ID:    str = ""
    DHAN_ACCESS_TOKEN: str = ""

    # Shoonya / Finvasia credentials (server-side only)
    SHOONYA_USER_ID: str = ""
    SHOONYA_PASSWORD: str = ""
    SHOONYA_TOTP_SECRET: str = ""
    SHOONYA_VENDOR_CODE: str = ""
    SHOONYA_API_SECRET: str = ""
    SHOONYA_IMEI: str = "algo-platform-v1"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

