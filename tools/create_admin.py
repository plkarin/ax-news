#!/usr/bin/env python3
"""An administrator account: the first one of a new install (sign-up is
closed, and a Google account waits for an administrator's approval).
Creates the account, or makes an existing one administrator and sets its
password.

    docker compose exec backend python tools/create_admin.py alice
    backend/venv/bin/python tools/create_admin.py alice          # without Docker

The password is asked for, or read from AXNEWS_ADMIN_PASSWORD."""
import asyncio
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv
load_dotenv(ROOT / "backend" / ".env")

import asyncpg
from auth import hash_password


async def main(username: str, password: str):
    c = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        row = await c.fetchrow("""
            INSERT INTO users (username, password_hash, is_admin, email_verified, approved, approved_at)
            VALUES ($1, $2, true, true, true, now())
            ON CONFLICT DO NOTHING RETURNING id""", username, hash_password(password))
        if row is None:
            await c.execute("""UPDATE users SET password_hash = $2, is_admin = true, approved = true,
                                   approved_at = coalesce(approved_at, now()) WHERE username = $1""",
                            username, hash_password(password))
            print(f"{username}: administrator, password set")
        else:
            print(f"{username}: administrator account created")
    finally:
        await c.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    pw = os.getenv("AXNEWS_ADMIN_PASSWORD") or getpass.getpass("Password (8 characters at least): ")
    if len(pw) < 8:
        sys.exit("The password needs 8 characters at least.")
    asyncio.run(main(sys.argv[1].strip(), pw))
