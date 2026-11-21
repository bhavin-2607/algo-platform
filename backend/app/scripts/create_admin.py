"""Create the first admin when the users table is empty.

The launcher sets FIRST_ADMIN_PASSWORD and prints that password once.
This command does not write the password to disk.
"""
import asyncio
import os
import sys

# Ensure backend directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Auto-detect virtualenv site-packages if running with system python
for venv_path in [
    os.path.join(BACKEND_DIR, ".venv"),
    os.path.join(BACKEND_DIR, "..", ".venv"),
]:
    if os.path.isdir(venv_path):
        import glob
        sp = glob.glob(os.path.join(venv_path, "lib", "python*", "site-packages"))
        for s in sp:
            if s not in sys.path:
                sys.path.insert(0, s)

from sqlalchemy import func, select

import app.models  # noqa: F401  (register tables before create_all)
from app.core.database import AsyncSessionLocal, init_db
from app.core.security import hash_password
from app.models.user import User, UserRole


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]

    await init_db()

    # 1. List users
    if "--list" in flags or "-l" in flags or (len(sys.argv) > 1 and sys.argv[1] == "list"):
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
            if not users:
                print("No users found in database.")
            else:
                print(f"Found {len(users)} user(s) in database:")
                for u in users:
                    print(f"  - Username: {u.username} | Email: {u.email} | Role: {u.role} | Active: {u.is_active} | MFA: {u.mfa_enabled}")
        return

    # 2. Parse username and password
    target_username = "admin"
    password = ""
    if len(args) == 1:
        password = args[0]
    elif len(args) >= 2:
        target_username = args[0]
        password = args[1]
    else:
        password = os.environ.get("FIRST_ADMIN_PASSWORD", "").strip()

    if len(password) < 8:
        print("Usage:", file=sys.stderr)
        print("  python backend/app/scripts/create_admin.py --list", file=sys.stderr)
        print("  python backend/app/scripts/create_admin.py <password>                 # creates or resets 'admin'", file=sys.stderr)
        print("  python backend/app/scripts/create_admin.py <username> <password>      # creates or resets specific user", file=sys.stderr)
        sys.exit(2)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where((User.username.ilike(target_username)) | (User.email.ilike(target_username)))
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            existing_user.hashed_password = hash_password(password)
            existing_user.is_active = True
            await db.commit()
            print(f"Successfully updated password for existing user '{existing_user.username}' ({existing_user.email}).")
            return

        role = UserRole.admin if target_username == "admin" else UserRole.trader
        email = f"{target_username}@example.com" if "@" not in target_username else target_username
        uname = target_username if "@" not in target_username else target_username.split("@")[0]
        db.add(User(
            email=email,
            username=uname,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
        ))
        await db.commit()
        print(f"Created user '{uname}' ({email}) with role '{role}'.")


if __name__ == "__main__":
    asyncio.run(main())
