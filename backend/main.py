import asyncio, hashlib, logging, os, re, html as html_lib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import asyncpg
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse as _JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

load_dotenv()

import freshrss
import db as database
import sources
from claude_proxy import call_claude
from auth import hash_password, verify_password, create_session, get_session_user, delete_session
from keyword_analysis import enrich_batch_static, enrich_article_static
from translation import translate_batch, translate_article
import json as json_lib
from collections import defaultdict
import time as _time
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

_login_attempts: dict = defaultdict(list)
_sync_attempts: dict = defaultdict(list)

def _check_rate_limit(store: dict, key: str, max_calls: int, window: int) -> bool:
    now = _time.time()
    store[key] = [t for t in store[key] if now - t < window]
    if len(store[key]) >= max_calls:
        return False
    store[key].append(now)
    return True

# ── Config ────────────────────────────────────────────────────────────────────

freshrss.BASE = os.getenv("FRESHRSS_BASE_URL")
freshrss.USER = os.getenv("FRESHRSS_USER")
freshrss.PASS = os.getenv("FRESHRSS_API_PASS")
CLAUDE_USER   = os.getenv("CLAUDE_USER", "cbrain")
DATABASE_URL  = os.getenv("DATABASE_URL")
LOG_FILE      = os.getenv("LOG_FILE", "/var/log/ax-news/backend.log")

# Google OAuth config
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "https://ax-news.com/api/auth/google/callback")

# Email config
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@ax-news.com")
APP_URL              = os.getenv("APP_URL", "https://ax-news.com")
INTERNAL_SYNC_TOKEN  = os.getenv("INTERNAL_SYNC_TOKEN", "")
VIEW_SALT = os.getenv("VIEW_SALT") or hashlib.sha256(("ax-news-views:" + INTERNAL_SYNC_TOKEN).encode()).hexdigest()

# In-memory token store (use Redis in production)
_email_tokens: dict = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ax-news")

pool: asyncpg.Pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    logger.info("Database pool created")
    yield
    await pool.close()

app = FastAPI(title="AX-NEWS API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # The pages and the API share one origin: no other site may read the API
    # with a reader's session.
    allow_origins=[os.getenv("APP_URL", "https://ax-news.com")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pages whose scripts still use inline handlers (onclick=…): they keep the
# old, permissive policy until they are rebuilt.
LEGACY_CSP_PAGES = {"/tv.html"}
_GOOGLE = "https://accounts.google.com https://apis.google.com"


class CSPNonceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)
        if request.url.path in LEGACY_CSP_PAGES:
            script = f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {_GOOGLE}; "
        else:
            # Only this response's own scripts run: an injected <script> or
            # onclick= does not.
            script = f"script-src 'self' 'nonce-{nonce}' {_GOOGLE}; "
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; " + script +
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://www.googleapis.com; "
            "frame-src https://accounts.google.com; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self';"
        )
        return response

app.add_middleware(CSPNonceMiddleware)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _asset_version() -> str:
    """Changes whenever a file under frontend/assets changes: appended to the
    pages' CSS and JS, so a browser never keeps last week's script."""
    newest = 0.0
    for f in (FRONTEND_DIR / "assets").rglob("*"):
        if f.is_file():
            newest = max(newest, f.stat().st_mtime)
    return hashlib.sha1(str(newest).encode()).hexdigest()[:10]


templates.env.globals["asset_version"] = _asset_version()
COOKIE_SECURE = os.getenv("APP_URL", "https://ax-news.com").startswith("https://")

@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = _time.time()
    response = await call_next(request)
    duration = (_time.time() - start) * 1000

    path = request.url.path
    if path.startswith("/api/") and path != "/api/health":
        try:
            token = request.cookies.get("ax_session")
            user_id = None
            username = None
            if token and pool:
                try:
                    user = await get_session_user(pool, token)
                    if user:
                        user_id = user["id"]
                        username = user["username"]
                except Exception:
                    pass

            article_id = None
            parts = path.split("/")
            for i, p in enumerate(parts):
                if p == "articles" and i + 1 < len(parts):
                    try:
                        article_id = int(parts[i + 1])
                    except Exception:
                        pass

            await pool.execute("""
                INSERT INTO access_logs
                  (user_id, username, ip_address, endpoint, method,
                   article_id, user_agent, status_code, duration_ms)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            """,
                user_id, username,
                request.client.host if request.client else "unknown",
                path, request.method, article_id,
                request.headers.get("user-agent", "")[:200],
                response.status_code, round(duration, 2)
            )
        except Exception as e:
            logger.warning(f"Access log error: {e}")

    return response

@app.get("/api/tv/feed")
async def tv_feed(limit: int = 150):
    """Public TV feed — only translated articles."""
    rows = await pool.fetch("""
        SELECT id, title, feed_source, category,
               published_at, ingested_at, content_raw, image_url, url,
               country_code, entities, sentiment, sentiment_score,
               original_lang, translation_status
        FROM articles
        WHERE published_at <= NOW()
          AND owner_user_id IS NULL
          AND published_at >= NOW() - INTERVAL '30 days'
          AND (translation_status = 'done' OR original_lang = 'en')
          AND title !~ '[가-힣]'
          AND title !~ '[\\u4e00-\\u9fff]'
          AND title !~ '[\\u3040-\\u309f]'
        ORDER BY published_at DESC
        LIMIT $1
    """, limit)
    import json as _json
    result = []
    for r in rows:
        row = dict(r)
        if isinstance(row.get('entities'), str):
            try:
                row['entities'] = _json.loads(row['entities'])
            except Exception:
                row['entities'] = []
        if row.get('entities') is None:
            row['entities'] = []
        result.append(serialize_row(row))
    return result

# ── Auth dependency ───────────────────────────────────────────────────────────

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("ax_session")
    if not token:
        raise HTTPException(401, "Non authentifié")
    user = await get_session_user(pool, token)
    if not user:
        raise HTTPException(401, "Session expirée")
    return user

async def get_optional_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("ax_session")
    if not token:
        return None
    return await get_session_user(pool, token)

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return user

async def require_admin_or_internal(request: Request) -> dict:
    """Admin session OR internal token from localhost (systemd timers)."""
    token = request.headers.get("x-internal-token", "")
    if INTERNAL_SYNC_TOKEN and token == INTERNAL_SYNC_TOKEN:
        client_ip = request.client.host if request.client else ""
        if client_ip in ("127.0.0.1", "::1"):
            return {"id": 0, "username": "internal", "is_admin": True}
    user = await get_current_user(request)  # raises 401 if no/invalid session
    if not user.get("is_admin"):
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return user

@app.api_route("/api/tv/refresh", methods=["GET", "POST"])
async def tv_refresh(request: Request, admin: dict = Depends(require_admin_or_internal)):
    """Admin-only TV feed refresh."""
    if request.method == "GET":
        return {"message": "POST to trigger refresh"}
    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            token = await freshrss.authenticate(client)
            items = await freshrss.fetch_articles(client, token, n=500)
        except Exception as e:
            return {"synced": 0, "error": str(e)}
    count = 0
    for item in items:
        art = freshrss.parse_article(item)
        if art["freshrss_id"]:
            await database.upsert_article(pool, art)
            count += 1
    translated = 0  # Translation moved to standalone worker
    from keyword_analysis import enrich_batch_static
    enriched = await enrich_batch_static(pool, limit=500)
    return {"synced": count, "translated": translated, "enriched": enriched}

# ── Models ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    article_id: int
    message: str

class ReadRequest(BaseModel):
    pass

class CreateUserRequest(BaseModel):
    username: str
    email: Optional[str] = None
    password: str

class DiscoverRequest(BaseModel):
    input: str

class AddSourceRequest(BaseModel):
    url: str
    name: Optional[str] = None
    category: Optional[str] = None
    kind: Optional[str] = None

class UpdateSourceRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    active: Optional[bool] = None

class OpmlRequest(BaseModel):
    opml: str

# ── Serialisation ─────────────────────────────────────────────────────────────

def serialize(obj):
    from datetime import datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bool):
        return obj
    return obj

def serialize_row(row: dict) -> dict:
    return {k: serialize(v) for k, v in row.items()}

# ── Public endpoints ──────────────────────────────────────────────────────────

# Read-only token for the TV dashboards' feed (backend/.env). Empty: those
# endpoints refuse every request.
TV_TOKEN = os.getenv("TV_TOKEN", "")

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/tv/articles")
async def tv_articles(token: str = "", limit: int = 100):
    """Public endpoint for TV dashboard — no session required."""
    if not TV_TOKEN or token != TV_TOKEN:
        raise HTTPException(403, "Invalid token")
    rows = await database.get_articles(pool, limit=limit, user_id=1)
    return [serialize_row(r) for r in rows]

@app.post("/api/tv/sync")
async def tv_sync(token: str = "", request: Request = None):
    """Public sync trigger for TV dashboard."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(_sync_attempts, client_ip, 1, 300):
        raise HTTPException(429, "Sync rate limited. Try again in 5 minutes.")
    if not TV_TOKEN or token != TV_TOKEN:
        raise HTTPException(403, "Invalid token")
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            token_fr = await freshrss.authenticate(client)
            items = await freshrss.fetch_articles(client, token_fr, n=200)
        except Exception as e:
            return {"synced": 0, "error": str(e)}
    count = 0
    for item in items:
        art = freshrss.parse_article(item)
        if art["freshrss_id"]:
            await database.upsert_article(pool, art)
            count += 1
    await pool.execute("""
        UPDATE articles
        SET translated_at = NULL, original_lang = NULL
        WHERE translated_at IS NOT NULL
          AND (title ~ '[가-힣]' OR title ~ '[一-鿿]'
               OR title ~ '[぀-ゟ]' OR title ~ '[가-힯]')
    """)
    translated = 0  # Translation moved to standalone worker
    enriched = await enrich_batch_static(pool, limit=500)
    return {"synced": count, "translated": translated, "enriched": enriched}

@app.post("/api/sync")
async def sync_articles(admin: dict = Depends(require_admin_or_internal)):
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            token = await freshrss.authenticate(client)
            items = await freshrss.fetch_articles(client, token, n=500)
        except Exception as e:
            logger.error(f"FreshRSS sync error: {e}")
            raise HTTPException(502, f"FreshRSS error: {e}")
    count = 0
    for item in items:
        art = freshrss.parse_article(item)
        if art["freshrss_id"]:
            await database.upsert_article(pool, art)
            count += 1
    logger.info(f"Synced {count} articles")
    await pool.execute("""
        UPDATE articles
        SET translated_at = NULL, original_lang = NULL
        WHERE translated_at IS NOT NULL
          AND (title ~ '[가-힣]' OR title ~ '[一-鿿]'
               OR title ~ '[぀-ゟ]' OR title ~ '[가-힯]')
    """)
    translated = 0  # Translation moved to standalone worker
    # Static keyword enrichment — fast, no AI calls
    enriched = await enrich_batch_static(pool, limit=500)
    logger.info(f"Synced {count}, translated {translated}, enriched {enriched}")
    return {"synced": count, "translated": translated, "enriched": enriched}

# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(req: LoginRequest, response: Response, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(_login_attempts, client_ip, 5, 300):
        raise HTTPException(429, "Too many login attempts. Try again in 5 minutes.")
    row = await pool.fetchrow(
        "SELECT id, username, email, is_admin, password_hash, approved FROM users WHERE username = $1",
        req.username
    )
    if not row or not row["password_hash"]:
        raise HTTPException(401, "Username or password not recognised.")
    if not verify_password(req.password, row["password_hash"]):
        raise HTTPException(401, "Username or password not recognised.")
    if not row.get("approved", True):
        raise HTTPException(403, "Your account is pending admin approval.")
    token = await create_session(pool, row["id"])
    response.set_cookie(
        key="ax_session", value=token,
        httponly=True, path="/", max_age=2592000, samesite="lax", secure=COOKIE_SECURE
    )
    return {"user_id": row["id"], "username": row["username"], "is_admin": row["is_admin"]}

@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("ax_session")
    if token:
        await delete_session(pool, token)
    response.delete_cookie("ax_session", path="/")
    return {"ok": True}

@app.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

# ── User management (admin) ───────────────────────────────────────────────────

@app.get("/api/users")
async def list_users(admin: dict = Depends(require_admin)):
    rows = await pool.fetch("""
        SELECT u.id, u.username, u.email, u.is_admin, u.created_at,
               COUNT(DISTINCT ur.article_id) AS articles_read
        FROM users u
        LEFT JOIN user_reads ur ON ur.user_id = u.id
        GROUP BY u.id ORDER BY u.id
    """)
    return [serialize_row(dict(r)) for r in rows]

@app.post("/api/users", status_code=201)
async def create_user(req: CreateUserRequest, admin: dict = Depends(require_admin)):
    existing = await pool.fetchrow("SELECT id FROM users WHERE username = $1", req.username)
    if existing:
        raise HTTPException(409, "This username is taken.")
    if len(req.password or "") < 8:
        raise HTTPException(400, "The password needs 8 characters or more.")
    ph = hash_password(req.password)
    # Opened by an administrator: approved at once (the column's default,
    # false, left such an account waiting for an approval nobody asked for).
    row = await pool.fetchrow("""
        INSERT INTO users (username, email, password_hash, approved, approved_at, approved_by)
        VALUES ($1, $2, $3, TRUE, NOW(), $4) RETURNING id, username
    """, req.username.strip(), req.email, ph, admin["id"])
    return dict(row)

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "Impossible de supprimer votre propre compte")
    result = await pool.execute("DELETE FROM users WHERE id = $1", user_id)
    if result == "DELETE 0":
        raise HTTPException(404, "Utilisateur introuvable")
    return {"ok": True}

# ── Profile ───────────────────────────────────────────────────────────────────

@app.get("/api/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    row = await pool.fetchrow("""
        SELECT u.username, u.email,
               (SELECT count(*) FROM user_reads ur WHERE ur.user_id = u.id)      AS articles_read,
               (SELECT count(*) FROM user_knowledge uk WHERE uk.user_id = u.id)  AS knowledge_count,
               (SELECT count(*) FROM user_feeds uf WHERE uf.user_id = u.id
                  AND uf.active AND uf.kind IS NOT NULL)                        AS feeds_count,
               (SELECT count(*) FROM user_saves us WHERE us.user_id = u.id)      AS saved_count
        FROM users u WHERE u.id = $1
    """, user["id"])
    return serialize_row(dict(row))

@app.get("/api/knowledge")
async def my_knowledge(user: dict = Depends(get_current_user)):
    """What the AI analyst explained to this reader (admin chat)."""
    return [serialize_row(r) for r in await database.get_user_knowledge(pool, user["id"])]


@app.post("/api/profile/password")
async def change_password(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    current = body.get("current_password", "")
    new_pw  = body.get("new_password", "")
    if not new_pw or len(new_pw) < 8:
        raise HTTPException(400, "The new password needs 8 characters or more.")
    row = await pool.fetchrow("SELECT password_hash FROM users WHERE id = $1", user["id"])
    if not row or not verify_password(current, row["password_hash"]):
        raise HTTPException(401, "The current password is not right.")
    await pool.execute(
        "UPDATE users SET password_hash = $1 WHERE id = $2",
        hash_password(new_pw), user["id"]
    )
    return {"ok": True}

# ── Articles (authenticated) ──────────────────────────────────────────────────

SCOPES = {"public", "mine", "all"}


@app.get("/api/articles")
async def list_articles(
    limit:    int = Query(50, ge=1, le=100),
    offset:   int = Query(0, ge=0, le=5000),
    category: Optional[str] = None,
    search:   Optional[str] = Query(None, max_length=200),
    scope:    str = "public",
    source:   Optional[str] = None,
    feed:     Optional[int] = None,
    saved:    bool = False,
    user:     Optional[dict] = Depends(get_optional_user),
):
    """The feed. scope: public (shared feeds), mine (the reader's own
    sources), all (both). feed: one of the reader's sources. saved: the
    articles the reader saved."""
    uid = user["id"] if user else 0
    if scope not in SCOPES:
        raise HTTPException(400, "Unknown scope")
    if (scope != "public" or feed or saved) and not uid:
        raise HTTPException(401, "Sign in to see your own sources")
    rows = await database.get_articles(
        pool, limit=limit, offset=offset, category=category, search=search,
        user_id=uid, scope="mine" if feed else scope, source=source, feed_id=feed,
        saved=saved)
    return [serialize_row(r) for r in rows]


@app.get("/api/articles/count")
async def count_new_articles(since: datetime, category: Optional[str] = None,
                             scope: str = "public",
                             user: Optional[dict] = Depends(get_optional_user)):
    """How many articles appeared after `since`: the "new stories" button."""
    uid = user["id"] if user else 0
    if scope not in SCOPES or (scope != "public" and not uid):
        scope = "public"
    n = await database.get_articles(pool, category=category, user_id=uid, scope=scope,
                                    since=since, count_only=True)
    return {"count": n}


@app.get("/api/articles/{article_id}")
async def get_article(article_id: int, user: Optional[dict] = Depends(get_optional_user)):
    uid = user["id"] if user else 0
    row = await database.get_article_by_id(pool, article_id, uid)
    if not row:
        raise HTTPException(404, "Article introuvable")
    html = row.pop("content_raw", "") or ""
    for k in ("original_content", "audio_summary_text", "audio_url", "audio_status",
              "audio_error", "audio_duration_seconds", "audio_generated_at", "freshrss_id"):
        row.pop(k, None)
    row["paragraphs"] = database.paragraphs(html)
    row["excerpt"] = database.excerpt(html)
    row["reading_minutes"] = database.reading_minutes(html)
    row["personal"] = row.get("owner_user_id") is not None
    return serialize_row(row)


@app.post("/api/articles/{article_id}/save")
async def save_article(article_id: int, user: dict = Depends(get_current_user)):
    if not await database.get_article_by_id(pool, article_id, user["id"]):
        raise HTTPException(404, "Article not found")
    await pool.execute("INSERT INTO user_saves (user_id, article_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                       user["id"], article_id)
    return {"saved": True}


@app.delete("/api/articles/{article_id}/save")
async def unsave_article(article_id: int, user: dict = Depends(get_current_user)):
    await pool.execute("DELETE FROM user_saves WHERE user_id = $1 AND article_id = $2", user["id"], article_id)
    return {"saved": False}

@app.post("/api/articles/{article_id}/read")
async def mark_read(article_id: int, user: dict = Depends(get_current_user)):
    await database.mark_read(pool, user["id"], article_id)
    return {"ok": True}

@app.post("/api/articles/{article_id}/view")
async def record_view(article_id: int, request: Request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    raw_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    # Salted, as the privacy page says: the hash of an IP alone can be reversed
    # by hashing every IPv4 address.
    ip_hash = hashlib.sha256((VIEW_SALT + raw_ip).encode()).hexdigest()
    result = await pool.execute(
        "INSERT INTO article_views (article_id, ip_hash) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        article_id, ip_hash
    )
    if result == "INSERT 0 1":
        await pool.execute("UPDATE articles SET view_count = view_count + 1 WHERE id = $1", article_id)
        incremented = True
    else:
        incremented = False
    row = await pool.fetchrow("SELECT view_count FROM articles WHERE id = $1", article_id)
    if not row:
        raise HTTPException(404, "Article not found")
    return {"views": row["view_count"], "counted": incremented}

@app.get("/api/categories")
async def list_categories(user: Optional[dict] = Depends(get_optional_user)):
    rows = await pool.fetch(f"""
        SELECT DISTINCT a.category FROM articles a
        WHERE a.category IS NOT NULL AND a.category != ''
          AND {database.PUBLIC} AND {' AND '.join(database.VISIBLE)}
        ORDER BY a.category
    """)
    return [r["category"] for r in rows]


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    if not user.get('is_admin'):
        raise HTTPException(403, "AI analysis is available for admin accounts only.")
    article = await database.get_article_by_id(pool, req.article_id, user["id"])
    if not article:
        raise HTTPException(404, "Article introuvable")

    session = await database.get_claude_session(pool, user["id"], req.article_id)
    if session:
        session_id = session["id"]
        messages   = session["messages"] if isinstance(session["messages"], list) else []
        knowledge  = session["knowledge_extracted"] if isinstance(session["knowledge_extracted"], list) else []
    else:
        session_id = await database.create_claude_session(pool, user["id"], req.article_id)
        messages   = []
        knowledge  = []

    clean_content = re.sub(r"<[^>]+>", " ", article.get("content_raw") or "")
    clean_content = html_lib.unescape(clean_content)[:3000]

    system_prompt = f"""You are an expert intelligence analyst helping {user['username']} understand tech news.

ARTICLE:
Title: {article['title']}
Source: {article.get('feed_source', '')}
Category: {article.get('category', '')}
Content: {clean_content}

YOUR ROLE:
- Always respond in English only. Never use any other language.
- Explain clearly and concisely
- Identify key implications and broader trends
- Be structured and insightful
- If a knowledge gap is identified, include:
  <KNOWLEDGE>{{"domain":"X","gap_identified":"Y","gap_resolved":"Z"}}</KNOWLEDGE>"""

    response_text, ku = await call_claude(
        system_prompt, messages, req.message, claude_user=CLAUDE_USER
    )

    messages.append({"role": "user",     "content": req.message})
    messages.append({"role": "assistant", "content": response_text})

    if ku:
        knowledge.append(ku)
        await database.save_knowledge_update(
            pool, user["id"], req.article_id,
            ku.get("domain", ""), ku.get("gap_identified", ""), ku.get("gap_resolved", "")
        )

    await database.save_claude_session(pool, session_id, messages, knowledge)
    await database.mark_read(pool, user["id"], req.article_id)

    return {"response": response_text, "knowledge_updated": ku, "session_id": session_id}

@app.post("/api/articles/{article_id}/chat")
async def chat_with_article(article_id: int, req: dict, user: dict = Depends(get_current_user)):
    """AI chat about an article — admin only. Uses Claude Code via cbrain user."""
    if not user.get("is_admin"):
        raise HTTPException(403, "AI analysis is available for admin accounts only.")

    article = await pool.fetchrow("""
        SELECT id, title, feed_source, category, url, content_raw
        FROM articles WHERE id = $1
    """, article_id)
    if not article:
        raise HTTPException(404, "Article not found")

    message = req.get("message", "").strip()
    if not message:
        raise HTTPException(400, "Message required")

    content_raw = article["content_raw"] or ""
    clean_content = re.sub(r'<[^>]+>', ' ', content_raw)
    clean_content = re.sub(r'\s+', ' ', clean_content).strip()[:2000]

    prompt = f"""You are an expert intelligence analyst. Always respond in English only.

ARTICLE:
Title: {article['title']}
Source: {article['feed_source'] or 'Unknown'}
Category: {article['category'] or 'Technology'}
Content: {clean_content}

USER QUESTION: {message}

Respond in English only. Be concise, structured and insightful. Max 250 words.

If this exchange reveals a genuine knowledge gap the user is filling (a concept,
acronym, technology, or context they didn't previously understand), append at
the very end of your response (on its own line, after your answer):
<KNOWLEDGE>{{"domain":"<topic area>","gap_identified":"<what was unclear>","gap_resolved":"<the explanation given>"}}</KNOWLEDGE>
Only include this tag if there is a genuine learning moment — do not force it
for simple factual lookups."""

    try:
        proc = await asyncio.create_subprocess_exec(
            '/usr/local/bin/claude', '--print', prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                **os.environ,
                'HOME': '/',
                'USER': 'cbrain',
            }
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode != 0:
            err = stderr.decode()[:200]
            logger.error(f"Claude Code error: {err}")
            raise HTTPException(500, f"AI error: {err}")
        reply = stdout.decode().strip()
        if not reply:
            raise HTTPException(500, "Empty response from AI")

        knowledge_updated = None
        knowledge_match = re.search(r'<KNOWLEDGE>(.*?)</KNOWLEDGE>', reply, re.DOTALL)
        if knowledge_match:
            try:
                kdata = json_lib.loads(knowledge_match.group(1))
                await database.save_knowledge_update(
                    pool, user["id"], article_id,
                    kdata.get("domain", ""), kdata.get("gap_identified", ""), kdata.get("gap_resolved", "")
                )
                knowledge_updated = kdata
            except Exception as ke:
                logger.warning(f"Failed to parse/store knowledge tag: {ke}")
            reply = re.sub(r'<KNOWLEDGE>.*?</KNOWLEDGE>', '', reply, flags=re.DOTALL).strip()

        return {"response": reply, "knowledge_updated": knowledge_updated}
    except asyncio.TimeoutError:
        raise HTTPException(504, "AI response timed out — try again")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(500, f"AI error: {str(e)[:100]}")

@app.get("/api/chat/{article_id}/history")
async def chat_history(article_id: int, user: dict = Depends(get_current_user)):
    session = await database.get_claude_session(pool, user["id"], article_id)
    if not session:
        return {"messages": [], "knowledge_extracted": []}
    return {
        "messages":            session["messages"],
        "knowledge_extracted": session["knowledge_extracted"],
    }

@app.get("/api/auth/google")
async def google_login():
    """Redirect to Google OAuth."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(501, "Google OAuth not configured")
    from urllib.parse import urlencode
    from fastapi.responses import RedirectResponse
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url)

@app.get("/api/auth/google/callback")
async def google_callback(code: str, request: Request):
    """Handle Google OAuth callback."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(501, "Google OAuth not configured")
    from fastapi.responses import RedirectResponse
    oauth_logger = logging.getLogger("ax-news-oauth")
    oauth_logger.warning(f"OAUTH_DEBUG: callback received, code prefix={code[:20]}")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        oauth_logger.warning(f"OAUTH_DEBUG: token exchange status={token_resp.status_code}, has_access_token={'access_token' in token_data}, error={token_data.get('error')}")
        if "access_token" not in token_data:
            raise HTTPException(400, f"Google auth failed: {token_data.get('error', 'unknown')}")
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )
        userinfo = userinfo_resp.json()

    email = userinfo.get("email", "").lower().strip()
    name = userinfo.get("name", "")
    oauth_logger.warning(f"OAUTH_DEBUG: userinfo email={email}, name={name}, verified={userinfo.get('verified_email')}")
    base_username = (name or email.split("@")[0]).replace(" ", "_")[:30]
    username = base_username

    if not email:
        raise HTTPException(400, "No email returned from Google")

    user = await pool.fetchrow("SELECT * FROM users WHERE lower(email) = $1", email)
    oauth_logger.warning(f"OAUTH_DEBUG: db lookup found={user is not None}, approved={user.get('approved') if user else 'N/A'}, id={user['id'] if user else 'N/A'}")

    if not user:
        import bcrypt
        random_pw = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()
        counter = 1
        while await pool.fetchrow("SELECT id FROM users WHERE username = $1", username):
            username = f"{base_username}{counter}"
            counter += 1
        user = await pool.fetchrow("""
            INSERT INTO users (username, email, password_hash, is_admin, email_verified, approved)
            VALUES ($1, $2, $3, false, true, false)
            RETURNING *
        """, username, email, random_pw)
        oauth_logger.warning(f"OAUTH_DEBUG: new user created id={user['id']}, redirecting to pending")
        return RedirectResponse("/login.html?pending=1")

    if not user.get("approved"):
        oauth_logger.warning(f"OAUTH_DEBUG: user id={user['id']} not approved, redirecting to pending")
        return RedirectResponse("/login.html?pending=1")

    session_token = secrets.token_urlsafe(32)
    await pool.execute("""
        INSERT INTO user_sessions (id, user_id, expires_at)
        VALUES ($1, $2, NOW() + INTERVAL '30 days')
    """, session_token, user["id"])
    oauth_logger.warning(f"OAUTH_DEBUG: session created for user id={user['id']}, setting cookie and redirecting")
    # The session cookie is set by the server only, HttpOnly: the callback
    # page used to write it from JavaScript as well, readable by any script.
    response = templates.TemplateResponse(request, "google_callback.html", {
        "csp_nonce": getattr(request.state, 'csp_nonce', ''),
    })
    response.set_cookie(
        key="ax_session",
        value=session_token,
        max_age=30 * 24 * 60 * 60,
        path="/",
        samesite="lax",
        httponly=True,
        secure=COOKIE_SECURE,
    )
    return response

def send_verification_email(email: str, token: str):
    """Send verification email."""
    if not SMTP_HOST or not SMTP_USER:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Verify your AX-NEWS account"
        msg["From"] = SMTP_FROM
        msg["To"] = email
        verify_url = f"{APP_URL}/api/auth/verify?token={token}"
        html = f"""
        <div style="font-family:system-ui;max-width:500px;margin:40px auto;
                    background:#0a0a0f;color:#e8f4ff;padding:32px;border-radius:12px;
                    border:1px solid #1e1e2e">
          <h2 style="color:#4d9fff;margin-bottom:8px">AX-NEWS</h2>
          <p style="color:#4a7aa8;margin-bottom:24px">Global Tech Intelligence</p>
          <p>Click the button below to verify your email address:</p>
          <a href="{verify_url}"
             style="display:inline-block;margin:20px 0;padding:12px 24px;
                    background:linear-gradient(135deg,#0047ff,#4d9fff);
                    color:#fff;text-decoration:none;border-radius:8px;font-weight:700">
            Verify Email
          </a>
          <p style="color:#4a7aa8;font-size:.8rem">
            This link expires in 24 hours.<br>
            If you did not create an account, ignore this email.
          </p>
        </div>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False

@app.post("/api/auth/register")
async def register(req: dict):
    """Registration is closed."""
    raise HTTPException(403, "Registration is currently closed")
    username = req.get("username", "").strip()
    email    = req.get("email", "").strip()
    password = req.get("password", "")
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    existing = await pool.fetchrow(
        "SELECT id FROM users WHERE username = $1 OR (email IS NOT NULL AND email = $2)",
        username, email or None)
    if existing:
        raise HTTPException(409, "Username or email already exists")
    import bcrypt
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    email_verified = not bool(email)
    user = await pool.fetchrow("""
        INSERT INTO users (username, email, password_hash, is_admin, email_verified)
        VALUES ($1, $2, $3, false, $4) RETURNING id
    """, username, email or None, pw_hash, email_verified)
    if email and SMTP_HOST:
        token = secrets.token_urlsafe(32)
        _email_tokens[token] = {
            "user_id": user["id"],
            "email": email,
            "expires": datetime.utcnow() + timedelta(hours=24)
        }
        send_verification_email(email, token)
        return {"message": "Account created. Check your email to verify."}
    return {"message": "Account created. You can now log in."}

@app.get("/api/auth/verify")
async def verify_email(token: str, response: Response):
    """Verify email address."""
    from fastapi.responses import HTMLResponse, RedirectResponse
    data = _email_tokens.get(token)
    if not data or data["expires"] < datetime.utcnow():
        return HTMLResponse("<h1>Invalid or expired token</h1>", status_code=400)
    await pool.execute(
        "UPDATE users SET email_verified = true WHERE id = $1", data["user_id"])
    _email_tokens.pop(token, None)
    return RedirectResponse("/?verified=1")

@app.get("/api/categories/tree")
async def categories_tree(user: Optional[dict] = Depends(get_optional_user)):
    uid = user["id"] if user else 0
    # The counts the feed can show: public articles of the last 30 days.
    rows = await pool.fetch(f"""
        SELECT category,
               COUNT(*) as total,
               COUNT(CASE WHEN ur.id IS NOT NULL THEN 1 END) as read_count,
               COUNT(*) FILTER (WHERE a.published_at > NOW() - INTERVAL '24 hours') AS today
        FROM articles a
        LEFT JOIN user_reads ur ON ur.article_id = a.id AND ur.user_id = $1
        WHERE a.category IS NOT NULL AND a.category != ''
          AND {database.PUBLIC} AND {' AND '.join(database.VISIBLE)}
        GROUP BY a.category
        ORDER BY a.category
    """, uid)
    return [{"category": r["category"], "total": r["total"], "read": r["read_count"],
             "today": r["today"]} for r in rows]

@app.post("/api/enrich")
async def enrich_articles(limit: int = 500, admin: dict = Depends(require_admin_or_internal)):
    """Static keyword enrichment — fast, no AI calls."""
    count = await enrich_batch_static(pool, limit=limit)
    return {"enriched": count}

@app.get("/api/entities")
async def list_entities(user: Optional[dict] = Depends(get_optional_user)):
    """Return all distinct entities with article counts and avg sentiment score."""
    rows = await pool.fetch("""
        SELECT e.entity,
               COUNT(*) as article_count,
               AVG(sentiment_score) as avg_score,
               SUM(CASE WHEN sentiment IN ('positive','very_positive','breakthrough') THEN 1 ELSE 0 END) as positive_count,
               SUM(CASE WHEN sentiment IN ('negative','very_negative') THEN 1 ELSE 0 END) as negative_count,
               MAX(published_at) as latest
        FROM articles, jsonb_array_elements_text(entities) e(entity)
        WHERE entities IS NOT NULL AND jsonb_array_length(entities) > 0
          AND owner_user_id IS NULL AND published_at > NOW() - INTERVAL '30 days'
        GROUP BY e.entity
        ORDER BY article_count DESC
        LIMIT 100
    """)
    return [serialize_row(dict(r)) for r in rows]

@app.get("/api/entities/{entity_name}")
async def entity_detail(entity_name: str, limit: int = 50,
                        user: Optional[dict] = Depends(get_optional_user)):
    """Return articles mentioning a specific entity + sentiment stats."""
    uid = user["id"] if user else 0
    rows = await pool.fetch("""
        SELECT a.id, a.title, a.feed_source, a.category, a.published_at,
               a.url, a.image_url, a.country_code, a.entities,
               a.sentiment, a.sentiment_score,
               (ur.id IS NOT NULL) as is_read
        FROM articles a
        LEFT JOIN user_reads ur ON ur.article_id = a.id AND ur.user_id = $1
        WHERE a.entities @> $2::jsonb AND a.owner_user_id IS NULL
          AND a.published_at <= NOW()
        ORDER BY a.published_at DESC
        LIMIT $3
    """, uid, json_lib.dumps([entity_name]), limit)

    articles = [serialize_row(dict(r)) for r in rows]

    last10 = articles[:10]
    sentiment_counts = {}
    for a in last10:
        s = a.get("sentiment", "neutral")
        sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

    positive_n = sum(sentiment_counts.get(s, 0) for s in ["positive", "very_positive", "breakthrough"])
    negative_n = sum(sentiment_counts.get(s, 0) for s in ["negative", "very_negative"])
    total_n = len(last10)
    score_pct = round((positive_n / total_n * 100) if total_n else 50)

    return {
        "entity": entity_name,
        "articles": articles,
        "stats": {
            "total_articles": len(articles),
            "last10_positive": positive_n,
            "last10_negative": negative_n,
            "last10_neutral": total_n - positive_n - negative_n,
            "sentiment_score_pct": score_pct,
            "sentiment_counts": sentiment_counts,
        }
    }

@app.get("/api/countries")
async def list_countries(user: Optional[dict] = Depends(get_optional_user)):
    """Return article counts by country."""
    rows = await pool.fetch("""
        SELECT country_code, COUNT(*) as count
        FROM articles
        WHERE country_code IS NOT NULL AND country_code != '' AND owner_user_id IS NULL
        GROUP BY country_code ORDER BY count DESC
    """)
    return [dict(r) for r in rows]

@app.post("/api/translate")
async def trigger_translate(limit: int = 20, admin: dict = Depends(require_admin_or_internal)):
    """Translate up to limit non-English articles."""
    count = await translate_batch(pool, limit=limit)
    return {"translated": count}

_OG = (re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I),
       re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I))


async def _og_image(url: str) -> Optional[str]:
    """The og:image of a page, fetched through sources.safe_get(): an
    article's URL can come from a reader's own source, so it gets the same
    guard as any address a user typed."""
    try:
        final, status, headers, body = await sources.safe_get(url, {"Accept": "text/html"})
    except sources.SourceError:
        return None
    if status >= 400:
        return None
    html = body[:60000].decode("utf-8", "replace")
    for rx in _OG:
        m = rx.search(html)
        if m and m.group(1).startswith("http"):
            return html_lib.unescape(m.group(1))
    return None


@app.get("/api/proxy/ogimage")
async def get_og_image(url: str, user: Optional[dict] = Depends(get_optional_user)):
    """og:image of an article's page, for a card without a picture. Only the
    URL of an article this reader may see is fetched."""
    if not url or not url.startswith("http"):
        raise HTTPException(400, "Invalid URL")
    uid = user["id"] if user else 0
    if not await pool.fetchval(
            "SELECT 1 FROM articles WHERE url = $1 AND (owner_user_id IS NULL OR owner_user_id = $2) LIMIT 1",
            url, uid):
        raise HTTPException(404, "Unknown article URL")
    img = await _og_image(url)
    if img:
        # Kept, so the next reader (and the reader view) has it at once.
        await pool.execute("UPDATE articles SET image_url = $1 WHERE url = $2 AND image_url IS NULL", img, url)
    return {"image_url": img}


@app.post("/api/fetch-images")
async def fetch_missing_images(limit: int = 30, admin: dict = Depends(require_admin_or_internal)):
    """Fetch og:image for articles that have no image_url."""
    rows = await pool.fetch("""
        SELECT id, url FROM articles
        WHERE image_url IS NULL AND url IS NOT NULL AND url != ''
          AND published_at > NOW() - INTERVAL '30 days'
        ORDER BY ingested_at DESC LIMIT $1
    """, limit)
    count = 0
    for row in rows:
        img = await _og_image(row["url"])
        if img:
            await pool.execute("UPDATE articles SET image_url = $1 WHERE id = $2", img, row["id"])
            count += 1
    return {"fetched": count}

@app.post("/api/articles/{article_id}/image")
async def save_article_image(article_id: int, data: dict):
    """Save og:image URL fetched by TV client back to DB."""
    image_url = data.get("image_url", "")
    if image_url and image_url.startswith("http"):
        await pool.execute(
            "UPDATE articles SET image_url = $1 WHERE id = $2 AND image_url IS NULL",
            image_url, article_id
        )
    return {"ok": True}

@app.delete("/api/purge")
async def purge_old_articles(admin: dict = Depends(require_admin_or_internal)):
    """Delete articles older than 30 days. A user's knowledge note keeps its
    text and loses its link to the article (user_knowledge.source_article has
    no ON DELETE rule, so the DELETE used to fail on the first such note)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                UPDATE user_knowledge SET source_article = NULL
                WHERE source_article IN (
                    SELECT id FROM articles
                    WHERE published_at < NOW() - INTERVAL '30 days')
            """)
            result = await conn.execute("""
                DELETE FROM articles
                WHERE published_at < NOW() - INTERVAL '30 days'
            """)
    deleted = int(result.split()[-1])
    logger.info(f"Purged {deleted} articles")
    return {"deleted": deleted}

@app.get("/api/admin/stats")
async def admin_stats(user: dict = Depends(require_admin)):
    """The administration's dashboard: the feed, the accounts, their sources."""
    row = await pool.fetchrow("""
        SELECT (SELECT count(*) FROM articles WHERE owner_user_id IS NULL
                  AND published_at > NOW() - INTERVAL '24 hours' AND published_at <= NOW()) AS last24h,
               (SELECT count(*) FROM articles WHERE owner_user_id IS NULL
                  AND published_at > NOW() - INTERVAL '30 days') AS month,
               (SELECT count(*) FROM articles WHERE translation_status = 'pending') AS translation_pending,
               (SELECT count(*) FROM users) AS users,
               (SELECT count(*) FROM users WHERE approved = false) AS pending,
               (SELECT count(*) FROM user_feeds WHERE kind IS NOT NULL) AS sources,
               (SELECT count(*) FROM user_feeds WHERE kind IS NOT NULL AND last_error IS NOT NULL) AS sources_failing,
               (SELECT count(*) FROM articles WHERE owner_user_id IS NOT NULL) AS personal_articles,
               (SELECT max(ingested_at) FROM articles WHERE owner_user_id IS NULL) AS last_ingest
    """)
    per_user = await pool.fetch("""
        SELECT u.id, count(f.id) AS sources, count(f.id) FILTER (WHERE f.last_error IS NOT NULL) AS failing
          FROM users u LEFT JOIN user_feeds f ON f.user_id = u.id AND f.kind IS NOT NULL
         GROUP BY u.id""")
    return {**serialize_row(dict(row)), "per_user": {r["id"]: {"sources": r["sources"], "failing": r["failing"]} for r in per_user}}


@app.get("/api/admin/pending-users")
async def get_pending_users(user: dict = Depends(require_admin)):
    rows = await pool.fetch("""
        SELECT id, username, email, created_at, email_verified
        FROM users WHERE approved = false
        ORDER BY created_at DESC
    """)
    return [serialize_row(dict(r)) for r in rows]

@app.post("/api/admin/users/{user_id}/approve")
async def approve_user(user_id: int, user: dict = Depends(require_admin)):
    await pool.execute("""
        UPDATE users SET approved = true, approved_at = NOW(), approved_by = $1
        WHERE id = $2
    """, user["id"], user_id)
    return {"approved": True}

@app.get("/sitemap.xml")
async def sitemap():
    """Dynamic XML sitemap for Google — enhanced with priorities."""
    from fastapi.responses import Response as FastAPIResponse

    rows = await pool.fetch("""
        SELECT id, title, published_at, category, feed_source
        FROM articles
        WHERE translation_status = 'done'
          AND owner_user_id IS NULL
          AND published_at <= NOW()
          AND published_at >= NOW() - INTERVAL '30 days'
          AND title !~ '[가-힣]'
          AND title !~ '[一-鿿]'
        ORDER BY published_at DESC
        LIMIT 2000
    """)

    cat_priority = {
        'AI': '0.9', 'Cybersecurity': '0.9', 'Semiconductors': '0.85',
        'Geopolitics_TechPolicy': '0.8', 'Hardware': '0.75',
        'Energy_GreenTech': '0.75', 'Cloud_Infrastructure': '0.75',
        'Tech_Market': '0.7', 'Research_Papers': '0.65',
        'Quant_Finance': '0.65',
    }

    base = "https://ax-news.com"
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    lines.append(f"""  <url>
    <loc>{base}/</loc>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>""")

    for r in rows:
        lastmod = r['published_at'].strftime('%Y-%m-%dT%H:%M:%S+00:00') if r['published_at'] else ''
        priority = cat_priority.get(r['category'], '0.6')
        lines.append(f"""  <url>
    <loc>{base}/?article={r['id']}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>never</changefreq>
    <priority>{priority}</priority>
  </url>""")

    lines.append('</urlset>')
    return FastAPIResponse(content='\n'.join(lines), media_type="application/xml")

@app.get("/news-sitemap.xml")
async def news_sitemap():
    """Google News sitemap — last 48 hours only."""
    from fastapi.responses import Response as FastAPIResponse

    rows = await pool.fetch("""
        SELECT id, title, published_at, feed_source, category
        FROM articles
        WHERE translation_status = 'done'
          AND owner_user_id IS NULL
          AND published_at <= NOW()
          AND published_at >= NOW() - INTERVAL '48 hours'
          AND title !~ '[가-힣]'
          AND title !~ '[一-鿿]'
        ORDER BY published_at DESC
        LIMIT 1000
    """)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">',
    ]

    base = "https://ax-news.com"
    for r in rows:
        pub = r['published_at'].strftime('%Y-%m-%dT%H:%M:%S+00:00') if r['published_at'] else ''
        title_safe = (r['title'] or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        lines.append(f"""  <url>
    <loc>{base}/?article={r['id']}</loc>
    <news:news>
      <news:publication>
        <news:name>AX-NEWS</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>{pub}</news:publication_date>
      <news:title>{title_safe}</news:title>
    </news:news>
  </url>""")

    lines.append('</urlset>')
    return FastAPIResponse(content='\n'.join(lines), media_type="application/xml")

@app.post("/api/admin/users/{user_id}/reject")
async def reject_user(user_id: int, user: dict = Depends(require_admin)):
    await pool.execute(
        "DELETE FROM users WHERE id = $1 AND is_admin = false", user_id)
    return {"rejected": True}

# ── Personal sources ──────────────────────────────────────────────────────────
# Each account's own feeds (backend/sources.py). Their articles are the
# account's alone (articles.owner_user_id).

MAX_SOURCES = int(os.getenv("MAX_SOURCES_PER_USER", "150"))
_discover_attempts: dict = defaultdict(list)
_refresh_attempts: dict = defaultdict(list)
SOURCE_FIELDS = """id, name, url, site_url, kind, category, active, added_at, last_fetched_at,
                   last_ok_at, last_error, error_count, item_count"""


async def _own_source(source_id: int, user: dict) -> dict:
    row = await pool.fetchrow(f"SELECT {SOURCE_FIELDS}, user_id, etag, last_modified FROM user_feeds WHERE id = $1 AND user_id = $2",
                              source_id, user["id"])
    if not row:
        raise HTTPException(404, "Source not found")
    return dict(row)


@app.get("/api/sources")
async def list_sources(user: dict = Depends(get_current_user)):
    rows = await pool.fetch(f"""
        SELECT {SOURCE_FIELDS},
               (SELECT count(*) FROM articles a WHERE a.user_feed_id = f.id
                  AND a.published_at > NOW() - INTERVAL '7 days') AS week_count,
               (SELECT max(published_at) FROM articles a WHERE a.user_feed_id = f.id) AS latest_at
          FROM user_feeds f WHERE user_id = $1 AND kind IS NOT NULL
         ORDER BY lower(name)""", user["id"])
    return [serialize_row(dict(r)) for r in rows]


@app.post("/api/sources/discover")
async def discover_sources(req: DiscoverRequest, user: dict = Depends(get_current_user)):
    """What the reader typed — a feed, a site, a YouTube channel, a subreddit,
    a Mastodon account, a GitHub repository, "hn" — turned into feeds."""
    if not _check_rate_limit(_discover_attempts, str(user["id"]), 12, 60):
        raise HTTPException(429, "Too many searches. Wait a minute.")
    text = (req.input or "").strip()
    if not text or len(text) > 500:
        raise HTTPException(400, "Type an address, a channel or a feed.")
    try:
        found = await asyncio.wait_for(sources.discover(text), 30)
    except sources.SourceError as e:
        raise HTTPException(422, str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, "The site took too long to answer.")
    mine = {r["url"] for r in await pool.fetch("SELECT url FROM user_feeds WHERE user_id = $1", user["id"])}
    for f in found:
        f["already"] = f["url"] in mine
    return found


async def _add_source(user: dict, url: str, name: Optional[str], category: Optional[str],
                      kind: Optional[str], fetch_now: bool = True) -> dict:
    count = await pool.fetchval("SELECT count(*) FROM user_feeds WHERE user_id = $1 AND kind IS NOT NULL", user["id"])
    if count >= MAX_SOURCES:
        raise HTTPException(409, f"You already follow {MAX_SOURCES} sources.")
    parsed = sources.recent_feed(url)
    if parsed is None:
        try:
            final, status, headers, body = await sources.safe_get(url, {"Accept": ", ".join(sources.FEED_TYPES)})
            if status >= 400:
                raise sources.SourceError(f"The feed answered HTTP {status}.")
            parsed = sources.parse_feed(final, body)
        except sources.SourceError as e:
            raise HTTPException(422, str(e))
    title = (name or "").strip()[:120] or parsed["title"]
    cat = (category or "").strip()[:60] or None
    row = await pool.fetchrow(f"""
        INSERT INTO user_feeds (user_id, freshrss_id, name, url, category, kind, site_url, active)
        VALUES ($1, $2, $3, $2, $4, $5, $6, TRUE)
        ON CONFLICT (user_id, freshrss_id) DO UPDATE
           SET active = TRUE, name = EXCLUDED.name, category = EXCLUDED.category,
               kind = EXCLUDED.kind
        RETURNING {SOURCE_FIELDS}, user_id, etag, last_modified""",
        user["id"], parsed["url"], title, cat, (kind or "rss")[:20], parsed["site_url"])
    feed = dict(row)
    if fetch_now:
        new, total = await sources.store_entries(pool, feed, parsed["entries"])
        await pool.execute("""UPDATE user_feeds SET last_fetched_at = now(), last_ok_at = now(),
                              item_count = $2, last_error = NULL, error_count = 0 WHERE id = $1""",
                           feed["id"], total)
        feed["item_count"] = total
    return feed


@app.post("/api/sources", status_code=201)
async def add_source(req: AddSourceRequest, user: dict = Depends(get_current_user)):
    feed = await _add_source(user, req.url.strip(), req.name, req.category, req.kind)
    feed.pop("etag", None); feed.pop("last_modified", None); feed.pop("user_id", None)
    return serialize_row(feed)


@app.patch("/api/sources/{source_id}")
async def update_source(source_id: int, req: UpdateSourceRequest, user: dict = Depends(get_current_user)):
    await _own_source(source_id, user)
    if req.name is not None and req.name.strip():
        await pool.execute("UPDATE user_feeds SET name = $1 WHERE id = $2", req.name.strip()[:120], source_id)
        await pool.execute("UPDATE articles SET feed_source = $1 WHERE user_feed_id = $2", req.name.strip()[:120], source_id)
    if req.category is not None:
        cat = req.category.strip()[:60] or None
        await pool.execute("UPDATE user_feeds SET category = $1 WHERE id = $2", cat, source_id)
        await pool.execute("UPDATE articles SET category = COALESCE($1, 'My_Sources') WHERE user_feed_id = $2", cat, source_id)
    if req.active is not None:
        await pool.execute("UPDATE user_feeds SET active = $1, error_count = 0 WHERE id = $2", req.active, source_id)
    return serialize_row(await _own_source(source_id, user) | {"etag": None, "last_modified": None})


@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: int, user: dict = Depends(get_current_user)):
    """The source and every article it brought (saved ones included)."""
    await _own_source(source_id, user)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""UPDATE user_knowledge SET source_article = NULL
                                  WHERE source_article IN (SELECT id FROM articles WHERE user_feed_id = $1)""", source_id)
            await conn.execute("DELETE FROM user_feeds WHERE id = $1 AND user_id = $2", source_id, user["id"])
    return {"ok": True}


@app.post("/api/sources/{source_id}/refresh")
async def refresh_source(source_id: int, user: dict = Depends(get_current_user)):
    if not _check_rate_limit(_refresh_attempts, f"{user['id']}:{source_id}", 2, 60):
        raise HTTPException(429, "This source was refreshed a moment ago.")
    feed = await _own_source(source_id, user)
    feed["user_id"] = user["id"]
    r = await asyncio.wait_for(sources.fetch_source(pool, feed), 45)
    return r


@app.get("/api/sources/opml")
async def export_opml(user: dict = Depends(get_current_user)):
    rows = await pool.fetch("SELECT name, url, site_url FROM user_feeds WHERE user_id = $1 AND kind IS NOT NULL ORDER BY lower(name)", user["id"])
    return Response(sources.opml_document(user["username"], [dict(r) for r in rows]),
                    media_type="text/x-opml",
                    headers={"Content-Disposition": 'attachment; filename="ax-news-sources.opml"'})


@app.post("/api/sources/opml")
async def import_opml(req: OpmlRequest, user: dict = Depends(get_current_user)):
    """Import an OPML file's feeds (the format every reader exports). Each is
    checked and added; its articles arrive with the next fetch (5 minutes)."""
    outlines = sources.opml_outlines(req.opml or "")[:MAX_SOURCES]
    if not outlines:
        raise HTTPException(422, "No feed found in this file.")
    added, failed = [], []
    for o in outlines:
        try:
            f = await asyncio.wait_for(_add_source(user, o["url"], o["name"], None, "rss", fetch_now=False), 25)
            added.append(f["name"])
        except (HTTPException, asyncio.TimeoutError) as e:
            failed.append({"url": o["url"], "error": getattr(e, "detail", "timeout")})
    return {"added": len(added), "failed": failed}


# ── Saved articles, display preferences, trending ─────────────────────────────

PREF_KEYS = {"view", "density", "theme", "hidden_categories", "pinned_categories", "scope", "open_in"}


@app.get("/api/prefs")
async def get_prefs(user: dict = Depends(get_current_user)):
    v = await pool.fetchval("SELECT prefs FROM user_prefs WHERE user_id = $1", user["id"])
    return json_lib.loads(v) if isinstance(v, str) else (v or {})


@app.put("/api/prefs")
async def put_prefs(prefs: dict, user: dict = Depends(get_current_user)):
    clean = {k: v for k, v in prefs.items() if k in PREF_KEYS}
    if len(json_lib.dumps(clean)) > 8000:
        raise HTTPException(413, "Too many preferences")
    await pool.execute("""
        INSERT INTO user_prefs (user_id, prefs, updated_at) VALUES ($1, $2::jsonb, now())
        ON CONFLICT (user_id) DO UPDATE SET prefs = user_prefs.prefs || EXCLUDED.prefs, updated_at = now()
    """, user["id"], json_lib.dumps(clean))
    return await get_prefs(user)


_trending_cache: dict = {"at": 0.0, "data": None}


@app.get("/api/trending")
async def trending():
    """What the last 24 hours talk about: entities and sources (public
    articles). Cached for 5 minutes."""
    if _trending_cache["data"] is not None and _time.time() - _trending_cache["at"] < 300:
        return _trending_cache["data"]
    ents = await pool.fetch("""
        SELECT e.entity, count(*) AS n, avg(sentiment_score) AS score
          FROM articles, jsonb_array_elements_text(entities) e(entity)
         WHERE owner_user_id IS NULL AND published_at > NOW() - INTERVAL '24 hours'
           AND published_at <= NOW()
         GROUP BY e.entity ORDER BY n DESC LIMIT 14""")
    srcs = await pool.fetch("""
        SELECT feed_source, count(*) AS n FROM articles
         WHERE owner_user_id IS NULL AND published_at > NOW() - INTERVAL '24 hours'
           AND published_at <= NOW() AND feed_source <> ''
         GROUP BY feed_source ORDER BY n DESC LIMIT 8""")
    total = await pool.fetchval("""SELECT count(*) FROM articles WHERE owner_user_id IS NULL
                                   AND published_at > NOW() - INTERVAL '24 hours' AND published_at <= NOW()""")
    data = {"entities": [serialize_row(dict(r)) for r in ents],
            "sources": [dict(r) for r in srcs], "last24h": total}
    _trending_cache.update(at=_time.time(), data=data)
    return data


# ── Pages ─────────────────────────────────────────────────────────────────────
# Jinja2 templates (backend/templates, on base.html), each response with its
# own CSP nonce.

def page(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, {"csp_nonce": getattr(request.state, "csp_nonce", ""), **ctx})


def _redirect(to: str):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(to, status_code=301)


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    return page(request, "index.html", active="feed")

@app.get("/saved", response_class=HTMLResponse)
async def saved_page(request: Request):
    return page(request, "index.html", active="saved")

@app.get("/mine", response_class=HTMLResponse)
async def mine_page(request: Request):
    return page(request, "index.html", active="mine")

@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    return page(request, "account.html", active="account")

@app.get("/login.html", response_class=HTMLResponse)
async def login_html(request: Request):
    return page(request, "login.html")

@app.get("/admin.html", response_class=HTMLResponse)
async def admin_html(request: Request):
    return page(request, "admin.html", active="admin")

@app.get("/tv.html", response_class=HTMLResponse)
async def tv_html(request: Request):
    return page(request, "tv.html")

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return page(request, "about.html")

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return page(request, "privacy.html")

@app.get("/architecture", response_class=HTMLResponse)
async def architecture_page(request: Request):
    return page(request, "architecture.html")

@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    return page(request, "contact.html")

@app.get("/landing.html", response_class=HTMLResponse)
async def landing_html(request: Request):
    return page(request, "landing.html")

@app.get("/site.webmanifest")
async def web_manifest():
    # nginx serves frontend/ by file extension, and .webmanifest is not one.
    from fastapi.responses import FileResponse
    return FileResponse(FRONTEND_DIR / "site.webmanifest", media_type="application/manifest+json")

# Old addresses
@app.get("/index.html")
async def index_html():
    return _redirect("/")

@app.get("/profile.html")
async def profile_html():
    return _redirect("/account")

@app.get("/about.html")
async def about_html():
    return _redirect("/about")

@app.get("/privacy.html")
async def privacy_html():
    return _redirect("/privacy")


# In production nginx serves frontend/ itself. For a preview or local work,
# AXNEWS_SERVE_STATIC=1 lets the backend serve it (registered last, so every
# route above wins).
if os.getenv("AXNEWS_SERVE_STATIC") == "1":
    from fastapi.responses import FileResponse

    @app.get("/{path:path}")
    async def static_file(path: str):
        f = (FRONTEND_DIR / path).resolve()
        if f.is_file() and FRONTEND_DIR.resolve() in f.parents and not f.name.endswith(".html"):
            return FileResponse(f)
        raise HTTPException(404, "Not found")
