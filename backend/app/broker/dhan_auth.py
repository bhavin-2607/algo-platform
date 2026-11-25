"""
Dhan Authentication Manager
============================
Handles automated token generation and renewal for individual traders.

Two methods supported:
1. RenewToken  — Renews active token for 24 more hours (simplest)
2. TOTP-based  — Fully automated: generates fresh token daily using PIN + TOTP

Setup for TOTP method:
  1. Login to web.dhan.co → My Profile → Access DhanHQ APIs
  2. Enable TOTP → scan QR code with Google Authenticator
  3. Add to .env:
       DHAN_PIN=123456          (your 6-digit Dhan PIN)
       DHAN_TOTP_SECRET=XXXX    (base32 secret from QR code)

Token renewal flow (runs daily at 7:45 AM IST via Celery Beat):
  - If TOTP configured → generateAccessToken → fresh 24h token
  - Else → RenewToken → extends current token 24h
  - New token saved to .env + runtime config
"""
import logging
import requests
from datetime import datetime
from app.core.config import settings

import socket
_orig = socket.getaddrinfo
socket.getaddrinfo = lambda h,p,f=0,t=0,pr=0,fl=0: _orig(h,p,socket.AF_INET,t,pr,fl)

logger = logging.getLogger(__name__)

DHAN_AUTH_URL = "https://auth.dhan.co"
DHAN_API_URL  = "https://api.dhan.co/v2"


def decode_jwt_token(token: str) -> dict:
    """
    Decode standard JWT payload without verifying signature (used for expiry inspection).
    Returns dict with iat, exp, dhanClientId, etc.
    """
    if not token or not isinstance(token, str):
        return {}
    parts = token.strip().split(".")
    if len(parts) < 2:
        return {}
    try:
        import base64
        import json
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")))
    except Exception:
        return {}


def sync_dhan_token_to_database(new_token: str, client_id: str | None = None):
    """Ensure the Dhan master account in PostgreSQL holds the active encrypted token."""
    try:
        import asyncio
        from app.core.database import AsyncSessionLocal
        from app.models.broker import BrokerAccount, BrokerName
        from app.core.security import encrypt_broker_token
        from sqlalchemy import select

        async def _do_sync():
            clean_tok = new_token.strip()
            enc = encrypt_broker_token(clean_tok)
            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(BrokerAccount).where(
                        BrokerAccount.broker == BrokerName.dhan,
                        BrokerAccount.is_active == True,
                    )
                )
                accounts = res.scalars().all()
                updated = False
                for acc in accounts:
                    if acc.account_role == "MASTER" or (client_id and acc.client_id == client_id) or not acc.client_id:
                        acc.encrypted_access_token = enc
                        if client_id and not acc.client_id:
                            acc.client_id = client_id
                        updated = True
                if updated:
                    await db.commit()
                    logger.info("Synchronized renewed Dhan token to database BrokerAccount")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do_sync())
        except RuntimeError:
            asyncio.run(_do_sync())
    except Exception as exc:
        logger.warning(f"Could not sync token to database: {exc}")


class DhanAuthManager:

    def __init__(self):
        self._client_id    = None
        self._access_token = None

    @property
    def client_id(self) -> str:
        return (self._client_id or settings.DHAN_CLIENT_ID or "").strip()

    @client_id.setter
    def client_id(self, val: str):
        self._client_id = val

    @property
    def access_token(self) -> str:
        return (self._access_token or settings.DHAN_ACCESS_TOKEN or "").strip()

    @access_token.setter
    def access_token(self, val: str):
        self._access_token = val

    # ── Method 1: RenewToken ─────────────────────────────────────────────────

    def renew_token(self) -> dict | None:
        """
        Renew current active token for 24 more hours.
        GET /v2/RenewToken — no body and no TOTP.
        NOTE: Only works if current token is still ACTIVE (not expired).
        If token is expired, this will fail — use generate_token_totp instead.
        """
        try:
            resp = requests.get(
                f"{DHAN_API_URL}/RenewToken",
                headers={
                    "access-token": self.access_token,
                    "dhanClientId": self.client_id,
                    "Accept":       "application/json",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning(f"RenewToken returned HTTP {resp.status_code}: {resp.text}")
                return None

            data = resp.json()

            # Check for expired token error
            err_code = str(data.get("errorCode", ""))
            if err_code in ("DH-901", "DH-902", "DH-906", "808"):
                logger.warning(f"Token expired/invalid ({err_code}) — RenewToken cannot extend expired tokens")
                return None

            new_token = (
                data.get("token") or
                data.get("accessToken") or
                data.get("access_token") or
                (data.get("data") or {}).get("token") or
                (data.get("data") or {}).get("accessToken")
            )

            if new_token:
                logger.info("Dhan token renewed via RenewToken")
                self._apply_token(new_token, expires_at=data.get("expiryTime"))
                return {
                    "access_token": new_token,
                    "method":       "renew",
                    "expires_at":   data.get("expiryTime"),
                }

            logger.error(f"RenewToken failed: {data}")
            return None

        except Exception as e:
            logger.error(f"RenewToken error: {e}")
            return None

    # ── Method 2: TOTP-based generation ─────────────────────────────────────

    def generate_token_totp(self) -> dict | None:
        """
        Generate a fresh 24h token using PIN + TOTP.
        Requires DHAN_PIN and DHAN_TOTP_SECRET in .env.
        GET https://auth.dhan.co/app/generateAccessToken
        """
        pin         = getattr(settings, "DHAN_PIN", "")
        totp_secret = getattr(settings, "DHAN_TOTP_SECRET", "")

        if not pin or not totp_secret:
            logger.info("DHAN_PIN/DHAN_TOTP_SECRET not set — skipping TOTP generation")
            return None

        try:
            import pyotp
            totp      = pyotp.TOTP(totp_secret)
            totp_code = totp.now()

            resp = requests.post(
                f"{DHAN_AUTH_URL}/app/generateAccessToken",
                params={
                    "dhanClientId": self.client_id,
                    "pin":          pin,
                    "totp":         totp_code,
                },
                headers={
                    "Accept": "application/json",
                },
                timeout=10,
            )
            data = resp.json()

            if "accessToken" in data:
                logger.info(f"Token generated via TOTP — expires: {data.get('expiryTime')}")
                new_token = data["accessToken"]
                self._apply_token(new_token, expires_at=data.get("expiryTime"))
                return {
                    "access_token": new_token,
                    "client_id":    data.get("dhanClientId", self.client_id),
                    "method":       "totp",
                    "expires_at":   data.get("expiryTime"),
                    "name":         data.get("dhanClientName"),
                }

            logger.error(f"generateAccessToken failed: {data}")
            return None

        except ImportError:
            logger.error("pyotp not installed — run: pip install pyotp --break-system-packages")
            return None
        except Exception as e:
            logger.error(f"generateAccessToken error: {e}")
            return None

    # ── Smart renewal (tries TOTP first, falls back to RenewToken) ───────────

    def auto_renew(self, max_retries: int = 3) -> dict | None:
        """
        Smart renewal with retry and fallback chain:
        1. TOTP generation (fresh token)
        2. RenewToken (extend existing)
        3. Retry up to max_retries times with 5 min gap
        4. Send alert if all fail
        """
        import time

        for attempt in range(1, max_retries + 1):
            logger.info(f"Token renewal attempt {attempt}/{max_retries}...")

            # Try TOTP first
            result = self.generate_token_totp()

            # Fallback to RenewToken
            if not result:
                result = self.renew_token()

            if result:
                self._apply_token(result["access_token"])
                # Clear any failure flag
                self._set_token_status("ok", result.get("expires_at"))
                logger.info(f"Token renewed via {result['method']}")
                return result

            if attempt < max_retries:
                wait = 300  # 5 minutes between retries
                logger.warning(f"Renewal attempt {attempt} failed — retrying in {wait}s...")
                time.sleep(wait)

        # All attempts failed
        logger.error("All token renewal attempts failed!")
        self._set_token_status("failed")
        self._send_failure_alert()
        return None

    def _set_token_status(self, status: str, expires_at: str = None):
        """Store token status in Redis for UI banner."""
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.set("dhan:token:status", status, ex=86400)
            if expires_at:
                r.set("dhan:token:expires", expires_at, ex=86400)
        except Exception as e:
            logger.warning(f"Could not set token status in Redis: {e}")

    def _send_failure_alert(self):
        """Alert admin when token renewal fails."""
        msg = (
            "DHAN TOKEN RENEWAL FAILED. Manual action required: "
            "1) Go to web.dhan.co -> My Profile -> Access DhanHQ APIs "
            "2) Generate new Access Token "
            "3) POST /api/dhan-auth/manual-token with new token"
        )
        logger.critical(msg)

        # Store alert in Redis for UI banner
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.set("dhan:token:alert", "RENEWAL_FAILED", ex=86400)
        except Exception:
            pass

        # Send email alert if SMTP configured
        smtp_host   = getattr(settings, "SMTP_HOST", "")
        alert_email = getattr(settings, "ALERT_EMAIL", "")
        if smtp_host and alert_email:
            try:
                import smtplib
                from email.mime.text import MIMEText
                email_body = MIMEText(
                    "Dhan access token renewal failed.\n\n"
                    "Action required:\n"
                    "1. Go to web.dhan.co -> My Profile -> Access DhanHQ APIs\n"
                    "2. Generate new Access Token\n"
                    "3. POST /api/dhan-auth/manual-token with new token"
                )
                email_body["Subject"] = "AlgoTrade: Dhan Token Renewal Failed"
                email_body["From"]    = alert_email
                email_body["To"]      = alert_email
                smtp = smtplib.SMTP(smtp_host, getattr(settings, "SMTP_PORT", 587))
                smtp.send_message(email_body)
                smtp.quit()
                logger.info("Alert email sent")
            except Exception as e:
                logger.warning(f"Email alert failed: {e}")

    def _apply_token(self, new_token: str, expires_at: str = None):
        """Update token in runtime config, database, Redis, and persist to .env."""
        # Update runtime
        settings.DHAN_ACCESS_TOKEN = new_token
        self.access_token          = new_token

        # Synchronize to database
        sync_dhan_token_to_database(new_token, self.client_id)

        from app.core.env_files import existing_env_files

        try:
            paths = existing_env_files()
            if not paths:
                logger.error("No .env file found to persist the Dhan token")
            else:
                for env_path in paths:
                    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
                    updated = []
                    found = False
                    for line in lines:
                        if line.startswith("DHAN_ACCESS_TOKEN="):
                            updated.append(f"DHAN_ACCESS_TOKEN={new_token}\n")
                            found = True
                        else:
                            updated.append(line)
                    if not found:
                        updated.append(f"\nDHAN_ACCESS_TOKEN={new_token}\n")
                    env_path.write_text("".join(updated), encoding="utf-8")
                    logger.info(f"Token persisted to {env_path}")
        except Exception as e:
            logger.error(f"Failed to persist token: {e}")

        # Update Redis status & clear alerts
        info = self.get_token_expiry_info()
        exp_str = info.get("expires_at_ist") or expires_at
        self._set_token_status("ok", exp_str)
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.delete("dhan:token:alert")
        except Exception:
            pass

    # ── Token health check ────────────────────────────────────────────────────

    def get_token_expiry_info(self) -> dict:
        """
        Inspect current Dhan access token JWT payload to extract exact issue and expiry timestamps.
        """
        import time
        from datetime import datetime, timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))

        tok = self.access_token
        if not tok:
            settings.reload_from_disk()
            tok = self.access_token

        payload = decode_jwt_token(tok)
        if not payload or "exp" not in payload:
            return {
                "has_token": bool(tok),
                "is_jwt": False,
                "is_valid_format": False,
                "issued_at_ts": None,
                "expires_at_ts": None,
                "issued_at_ist": None,
                "expires_at_ist": None,
                "seconds_remaining": -1,
                "hours_remaining": -1.0,
                "is_expired": True,
                "is_expiring_soon": False,
            }

        iat_ts = payload.get("iat")
        exp_ts = payload.get("exp")
        now_ts = int(time.time())
        seconds_remaining = max(0, exp_ts - now_ts) if exp_ts else 0
        hours_remaining = round(seconds_remaining / 3600.0, 2)
        is_expired = (exp_ts <= now_ts) if exp_ts else True
        is_expiring_soon = (not is_expired) and (hours_remaining <= 3.5)

        iat_ist = datetime.fromtimestamp(iat_ts, ist).strftime("%Y-%m-%d %H:%M:%S IST") if iat_ts else None
        exp_ist = datetime.fromtimestamp(exp_ts, ist).strftime("%Y-%m-%d %H:%M:%S IST") if exp_ts else None

        return {
            "has_token": True,
            "is_jwt": True,
            "is_valid_format": True,
            "client_id": payload.get("dhanClientId", self.client_id),
            "issued_at_ts": iat_ts,
            "expires_at_ts": exp_ts,
            "issued_at_ist": iat_ist,
            "expires_at_ist": exp_ist,
            "seconds_remaining": seconds_remaining,
            "hours_remaining": hours_remaining,
            "is_expired": is_expired,
            "is_expiring_soon": is_expiring_soon,
        }

    def is_token_valid(self) -> bool:
        """Quick check if current token is still valid. Auto-reloads from .env if disk changed."""
        cid = self.client_id
        token = self.access_token

        if not cid or not token:
            settings.reload_from_disk()
            cid = self.client_id
            token = self.access_token

        if not cid or not token:
            return False

        try:
            resp = requests.get(
                f"{DHAN_API_URL}/fundlimit",
                headers={
                    "access-token": token,
                    "client-id":    cid,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return True

            # If failed (e.g. 401 Unauthorized), check if .env on disk has a newly updated token
            prev_token = token
            settings.reload_from_disk()
            if self.access_token and self.access_token != prev_token:
                logger.info("Detected updated Dhan token on disk — verifying new token...")
                retry_resp = requests.get(
                    f"{DHAN_API_URL}/fundlimit",
                    headers={
                        "access-token": self.access_token,
                        "client-id":    self.client_id,
                    },
                    timeout=10,
                )
                if retry_resp.status_code == 200:
                    logger.info("New Dhan token on disk is valid and active.")
                    return True

            return False
        except Exception as e:
            logger.warning(f"Dhan token validation request error: {e}")
            return False

    def is_token_expiring_soon(self, hours: float = 3.5) -> bool:
        """Check if active token expires within the given hours."""
        info = self.get_token_expiry_info()
        if not info["is_jwt"]:
            return True
        if info["is_expired"]:
            return False
        return 0 < info["hours_remaining"] <= hours

    def check_and_proactively_renew(self) -> dict | None:
        """
        Proactively renew token if within 3.5 hours of expiration or expired.
        """
        settings.reload_from_disk()
        info = self.get_token_expiry_info()

        if info.get("is_expiring_soon"):
            logger.info(
                f"Dhan token is expiring soon ({info['hours_remaining']}h remaining, exp: {info['expires_at_ist']}) — renewing..."
            )
            res = self.renew_token()
            if not res:
                res = self.auto_renew(max_retries=2)
            return res

        if info.get("is_expired"):
            pin = getattr(settings, "DHAN_PIN", "")
            totp_secret = getattr(settings, "DHAN_TOTP_SECRET", "")
            if pin and totp_secret:
                logger.warning("Dhan token has expired. Generating fresh token via TOTP...")
                return self.generate_token_totp()

        return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_auth_manager: DhanAuthManager | None = None

def get_auth_manager() -> DhanAuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = DhanAuthManager()
    return _auth_manager
