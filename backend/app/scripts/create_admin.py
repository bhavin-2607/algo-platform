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
    if len(password) < 8:
        print("FIRST_ADMIN_PASSWORD must be at least 8 characters", file=sys.stderr)
        sys.exit(2)
    await init_db()
    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
        if count:
            print("Users already exist. No admin was created.")
            return
        db.add(User(
            email="admin@localhost",
            username="admin",
            hashed_password=hash_password(password),
            role=UserRole.admin,
            is_active=True,
        ))
        await db.commit()
        print("Created admin user 'admin' (admin@localhost).")


if __name__ == "__main__":
    asyncio.run(main())
