"""Create the first admin when the users table is empty.

The launcher sets FIRST_ADMIN_PASSWORD and prints that password once.
This command does not write the password to disk.
"""
import asyncio
import os
import sys

from sqlalchemy import func, select

import app.models  # noqa: F401  (register tables before create_all)
from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_password
from app.models.user import User, UserRole


async def main() -> None:
    password = os.environ.get("FIRST_ADMIN_PASSWORD", "").strip()
    if not password and len(sys.argv) > 1:
        password = sys.argv[1].strip()

    if len(password) < 8:
        print("Usage: python backend/app/scripts/create_admin.py <password> (min 8 chars) or set FIRST_ADMIN_PASSWORD env var.", file=sys.stderr)
        sys.exit(2)

    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        existing_admin = result.scalar_one_or_none()
        if existing_admin:
            existing_admin.hashed_password = hash_password(password)
            existing_admin.is_active = True
            await db.commit()
            print("Successfully updated password for existing admin user 'admin'.")
            return

        db.add(User(
            email="admin@example.com",
            username="admin",
            hashed_password=hash_password(password),
            role=UserRole.admin,
            is_active=True,
        ))
        await db.commit()
        print("Created admin user 'admin' (admin@example.com).")


if __name__ == "__main__":
    asyncio.run(main())
