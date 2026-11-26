from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT:   str = "development"
    SECRET_KEY:    str = "change-me-in-production"
    JWT_SECRET:    str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ENCRYPTION_KEY:str = "change-me-32-bytes-key-here!!!!"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 43200  # 30 days
    REFRESH_TOKEN_EXPIRE_DAYS:    int = 30

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://algo_user:password@localhost/algo_platform"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:8000",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5173",
        "*",
    ]

    # ── Live trading safety ───────────────────────────────────────────────────
    # Live orders require explicit enable + valid Dhan credentials.
    LIVE_TRADING_ENABLED: bool = False
    ORDER_FILL_TIMEOUT_SEC: int = 30
    ORDER_FILL_POLL_INTERVAL_SEC: float = 0.5

    @field_validator("ORDER_FILL_TIMEOUT_SEC", mode="before")
    @classmethod
    def validate_order_timeout(cls, v):
        if v is None or str(v).strip() == "":
            return 30
        return int(v)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v or not str(v).strip():
            return "postgresql+asyncpg://algo_user:password@localhost/algo_platform"
        v = str(v).strip()
        needs_check = "@postgres:" in v or "@postgres/" in v or "//postgres:" in v or "//postgres/" in v
        if needs_check:
            import socket
            try:
                socket.getaddrinfo("postgres", 5432)
            except Exception:
                for pat in ["@postgres:", "@postgres/", "//postgres:", "//postgres/"]:
                    v = v.replace(pat, pat.replace("postgres", "localhost"))
        return v

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not v or not str(v).strip():
            return "redis://localhost:6379/0"
        v = str(v).strip()
        needs_check = "@redis:" in v or "@redis/" in v or "//redis:" in v or "//redis/" in v
        if needs_check:
            import socket
            try:
                socket.getaddrinfo("redis", 6379)
            except Exception:
                for pat in ["@redis:", "@redis/", "//redis:", "//redis/"]:
                    v = v.replace(pat, pat.replace("redis", "localhost"))
        return v

    # ── Dhan (primary broker) ─────────────────────────────────────────────────
    DHAN_PIN:         str = ""
    DHAN_TOTP_SECRET: str = ""
    SMTP_HOST:        str = ""   # optional email alerts
    SMTP_PORT:        int = 587
    ALERT_EMAIL:      str = ""
    DHAN_CLIENT_ID:    str = ""
    DHAN_ACCESS_TOKEN: str = ""
    DHAN_FORCE_IPV4:   bool = True

    # Operator alerts (optional). Empty values keep alerts in logs and Redis only.
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID:   str = ""
    FEED_STALE_SEC:     int = 90
    MARKET_POLLER_INTERVAL_SECONDS: float = 1.0

    def reload_from_disk(self):
        """Re-read credentials and settings directly from .env files on disk without restarting."""
        from app.core.env_files import existing_env_files
        for env_path in existing_env_files():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if hasattr(self, k):
                            current_val = getattr(self, k)
                            if isinstance(current_val, bool):
                                setattr(self, k, v.lower() in ("true", "1", "yes"))
                            elif isinstance(current_val, int):
                                try:
                                    setattr(self, k, int(v))
                                except ValueError:
                                    pass
                            elif isinstance(current_val, float):
                                try:
                                    setattr(self, k, float(v))
                                except ValueError:
                                    pass
                            else:
                                if k == "DATABASE_URL":
                                    v = self.validate_database_url(v)
                                elif k == "REDIS_URL":
                                    v = self.validate_redis_url(v)
                                setattr(self, k, v)
            except Exception:
                pass

    class Config:
        from app.core.env_files import env_file_candidates
        _candidates = [str(p) for p in env_file_candidates()]
        env_file = _candidates if _candidates else ".env"
        extra    = "ignore"


settings = Settings()
