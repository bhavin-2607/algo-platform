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

logger = logging.getLogger(__name__)

DHAN_AUTH_URL = "https://auth.dhan.co"
DHAN_API_URL  = "https://api.dhan.co/v2"


class DhanAuthManager:

    def __init__(self):
        self.client_id    = settings.DHAN_CLIENT_ID
        self.access_token = settings.DHAN_ACCESS_TOKEN

    # ── Method 1: RenewToken ─────────────────────────────────────────────────

    def renew_token(self) -> dict | None:
        """
        Renew current active token for 24 more hours.
        POST /v2/RenewToken — no TOTP needed.
        NOTE: Only works if current token is still ACTIVE (not expired).
        If token is expired, this will fail — use generate_token_totp instead.
        """
        try:
            resp = requests.post(
                f"{DHAN_API_URL}/RenewToken",
                headers={
                    "access-token": self.access_token,
                    "client-id":    self.client_id,   # correct header per Dhan docs
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            data = resp.json()

            # Check for expired token error
            err_code = str(data.get("errorCode", ""))
            if err_code in ("DH-901", "DH-902", "808"):
                logger.warning("Token already expired — RenewToken cannot extend expired tokens")
                return None

            new_token = (
                data.get("accessToken") or
                data.get("access_token") or
                (data.get("data") or {}).get("accessToken")
            )

            if new_token:
                logger.info("✅ Dhan token renewed via RenewToken")
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
                timeout=10,
            )
            data = resp.json()

            if "accessToken" in data:
                logger.info(f"✅ Token generated via TOTP — expires: {data.get('expiryTime')}")
                return {
                    "access_token": data["accessToken"],
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
                logger.info(f"✅ Token renewed via {result['method']}")
                return result

            if attempt < max_retries:
                wait = 300  # 5 minutes between retries
                logger.warning(f"Renewal attempt {attempt} failed — retrying in {wait}s...")
                time.sleep(wait)

        # All attempts failed
        logger.error("❌ All token renewal attempts failed!")
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

    def _apply_token(self, new_token: str):
        """Update token in runtime config and persist to .env."""
        # Update runtime
        settings.DHAN_ACCESS_TOKEN = new_token
        self.access_token          = new_token

        # Persist to .env
        import os
        env_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", ".env"
        )
        env_path = os.path.abspath(env_path)

        if not os.path.exists(env_path):
            # Try backend .env
            env_path = os.path.join(
                os.path.dirname(__file__), "..", "..", ".env"
            )
            env_path = os.path.abspath(env_path)

        try:
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()

                updated = []
                found   = False
                for line in lines:
                    if line.startswith("DHAN_ACCESS_TOKEN="):
                        updated.append(f"DHAN_ACCESS_TOKEN={new_token}\n")
                        found = True
                    else:
                        updated.append(line)

                if not found:
                    updated.append(f"\nDHAN_ACCESS_TOKEN={new_token}\n")

                with open(env_path, "w") as f:
                    f.writelines(updated)

                logger.info(f"Token persisted to {env_path}")
        except Exception as e:
            logger.error(f"Failed to persist token: {e}")

    # ── Token health check ────────────────────────────────────────────────────

    def is_token_valid(self) -> bool:
        """Quick check if current token is still valid."""
        if not self.access_token or not self.client_id:
            return False
        try:
            resp = requests.get(
                f"{DHAN_API_URL}/fundlimit",
                headers={
                    "access-token": self.access_token,
                    "client-id":    self.client_id,
                },
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def is_token_expiring_soon(self, hours: int = 2) -> bool:
        """
        RenewToken only works on ACTIVE tokens.
        We should renew BEFORE expiry (e.g. at 7:45 AM when token expires at ~same time).
        This checks if we should proactively renew.
        """
        # Since we can't check expiry time without storing it,
        # always attempt renewal if called during scheduled window
        return True


# ── Singleton ─────────────────────────────────────────────────────────────────

_auth_manager: DhanAuthManager | None = None

def get_auth_manager() -> DhanAuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = DhanAuthManager()
    return _auth_manager
