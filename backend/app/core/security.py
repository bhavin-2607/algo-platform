from datetime import datetime, timedelta
import base64
import pyotp
import bcrypt
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("about", (), {"__version__": getattr(bcrypt, "__version__", "4.0.0")})

from jose import jwt
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Fernet requires 32-url-safe-base64-encoded bytes
_raw_key = settings.ENCRYPTION_KEY[:32].encode().ljust(32, b"0")
_fernet_key = base64.urlsafe_b64encode(_raw_key)
fernet = Fernet(_fernet_key)


def hash_password(password: str) -> str:
    try:
        return pwd_context.hash(password)
    except Exception:
        return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload["type"] = "refresh"
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def encrypt_broker_token(token: str) -> str:
    """AES-encrypt broker access tokens before storing in DB."""
    return fernet.encrypt(token.encode()).decode()


def decrypt_broker_token(encrypted: str) -> str:
    """Decrypt broker access token for runtime use."""
    return fernet.decrypt(encrypted.encode()).decode()


def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def verify_mfa_token(secret: str, token: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(token)
