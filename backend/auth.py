import bcrypt, secrets

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

async def create_session(pool, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    await pool.execute("""
        INSERT INTO user_sessions (id, user_id)
        VALUES ($1, $2)
    """, token, user_id)
    return token

async def get_session_user(pool, token: str) -> dict | None:
    row = await pool.fetchrow("""
        SELECT u.id, u.username, u.email, u.is_admin
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = $1 AND s.expires_at > NOW()
    """, token)
    return dict(row) if row else None

async def delete_session(pool, token: str):
    await pool.execute("DELETE FROM user_sessions WHERE id = $1", token)
