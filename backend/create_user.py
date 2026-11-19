#!/usr/bin/env python3
"""
Create or Update User CLI
=========================
Usage:
  python create_user.py <email> <username> <password> [--role admin|trader]

Example:
  python create_user.py trader@algo.com trader Trader@123 --role admin
"""
import sys
import os
import argparse
import asyncio

# Ensure backend root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, init_db
from app.models.user import User, UserRole
from app.core.security import hash_password


async def create_or_update_user(email: str, username: str, password: str, role_str: str):
    await init_db()
    role = UserRole.admin if role_str.lower() == "admin" else UserRole.trader

    async with AsyncSessionLocal() as db:
        # Check if user exists by email or username
        res = await db.execute(
            select(User).where((User.email == email) | (User.username == username))
        )
        user = res.scalar_one_or_none()

        if user:
            print(f"[INFO] User already exists (ID: {user.id}, Email: {user.email}, Username: {user.username}).")
            user.email = email
            user.username = username
            user.hashed_password = hash_password(password)
            user.role = role
            user.is_active = True
            await db.commit()
            print(f"[SUCCESS] Successfully updated user credentials and role to '{role.value}' for {email}!")
        else:
            new_user = User(
                email=email,
                username=username,
                hashed_password=hash_password(password),
                role=role,
                is_active=True,
            )
            db.add(new_user)
            await db.commit()
            print(f"[SUCCESS] Successfully created {role.value} user: {email} (username: {username})")


def main():
    parser = argparse.ArgumentParser(description="Create or update user in Algo Platform")
    parser.add_argument("email", help="User email address")
    parser.add_argument("username", help="User username")
    parser.add_argument("password", help="User password")
    parser.add_argument("--role", default="admin", choices=["admin", "trader"], help="Role (admin or trader)")

    args = parser.parse_args()
    asyncio.run(create_or_update_user(args.email, args.username, args.password, args.role))


if __name__ == "__main__":
    main()
