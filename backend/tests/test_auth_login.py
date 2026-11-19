import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from fastapi import HTTPException

from app.api.routes.auth import login
from app.schemas.auth import LoginRequest
from app.models.user import User, UserRole
from app.core.security import hash_password


class TestAuthLogin(unittest.TestCase):
    def test_login_by_username_success(self):
        """Verify successful login using username."""
        import asyncio

        hashed = hash_password("SuperSecret123")
        user = User(
            id=uuid.uuid4(),
            email="trader@example.com",
            username="alphatrader",
            hashed_password=hashed,
            role=UserRole.trader,
            is_active=True,
            mfa_enabled=False,
        )

        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_res

        # Test login with exact username
        req = LoginRequest(username="alphatrader", password="SuperSecret123")
        res = asyncio.run(login(payload=req, db=mock_db))
        self.assertIsNotNone(res.access_token)
        self.assertIsNotNone(res.refresh_token)
        self.assertEqual(res.token_type, "bearer")

    def test_login_by_email_backwards_compatible(self):
        """Verify that login by email remains backwards compatible."""
        import asyncio

        hashed = hash_password("AdminPass456")
        user = User(
            id=uuid.uuid4(),
            email="admin@platform.com",
            username="admin",
            hashed_password=hashed,
            role=UserRole.admin,
            is_active=True,
            mfa_enabled=False,
        )

        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_res

        # Test login with email in payload
        req = LoginRequest(email="admin@platform.com", password="AdminPass456")
        res = asyncio.run(login(payload=req, db=mock_db))
        self.assertIsNotNone(res.access_token)
        self.assertIsNotNone(res.refresh_token)

    def test_login_invalid_password(self):
        """Verify 401 when password is wrong."""
        import asyncio

        hashed = hash_password("CorrectPassword")
        user = User(
            id=uuid.uuid4(),
            email="user@test.com",
            username="myuser",
            hashed_password=hashed,
            role=UserRole.trader,
            is_active=True,
        )

        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_res

        req = LoginRequest(username="myuser", password="WrongPassword")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(login(payload=req, db=mock_db))
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid credentials")

    def test_login_missing_identifier(self):
        """Verify 400 when neither username nor email is provided."""
        import asyncio

        mock_db = AsyncMock()
        req = LoginRequest(password="SomePassword")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(login(payload=req, db=mock_db))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Username or email is required", ctx.exception.detail)

    def test_login_deactivated_account(self):
        """Verify 403 when user account is deactivated."""
        import asyncio

        hashed = hash_password("ValidPassword")
        user = User(
            id=uuid.uuid4(),
            email="disabled@test.com",
            username="disableduser",
            hashed_password=hashed,
            role=UserRole.trader,
            is_active=False,
        )

        mock_db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_res

        req = LoginRequest(username="disableduser", password="ValidPassword")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(login(payload=req, db=mock_db))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "Account is deactivated")


if __name__ == "__main__":
    unittest.main()
