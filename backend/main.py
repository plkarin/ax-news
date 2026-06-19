import asyncio, logging, os, re, html as html_lib
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

load_dotenv()

import freshrss
import db as database
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
APP_URL   = os.getenv("APP_URL", "https://ax-news.com")

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CSPNonceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # login.html uses inline onclick= handlers; browsers ignore unsafe-inline
        # when a nonce is present, so skip nonce generation for this page.
        if request.url.path == '/login.html':
            request.state.csp_nonce = ''
            response = await call_next(request)
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://accounts.google.com https://apis.google.com; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self' https://accounts.google.com "
                "https://oauth2.googleapis.com https://www.googleapis.com; "
                "frame-src https://accounts.google.com; "
                "object-src 'none'; base-uri 'self'; form-action 'self';"
            )
            return response

        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://accounts.google.com https://apis.google.com; "
            "style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' data: https: blob:; "
            f"font-src 'self' data:; "
            f"connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://www.googleapis.com; "
            f"frame-src https://accounts.google.com; "
            f"object-src 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self';"
        )
        return response

app.add_middleware(CSPNonceMiddleware)

templates = Jinja2Templates(directory="/opt/ax-news/backend/templates")

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

@app.post("/api/tv/translate")
async def tv_translate(token: str = "", limit: int = 50):
    """Public translation endpoint for worker — TV token auth."""
    if token != "ax-news-tv-readonly-2026":
        raise HTTPException(403, "Not authorized")
    count = await translate_batch(pool, limit=limit)
    return {"translated": count}

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

@app.post("/api/tv/refresh")
async def tv_refresh():
    """Public TV refresh — no token in browser."""
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

@app.post("/api/tv/translate-public")
async def tv_translate_public(limit: int = 50):
    count = await translate_batch(pool, limit=limit)
    return {"translated": count}

# ── Auth dependency ───────────────────────────────────────────────────────────

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("ax_session")
    if not token:
        raise HTTPException(401, "Non authentifié")
    user = await get_session_user(pool, token)
    if not user:
        raise HTTPException(401, "Session expirée")
    return user

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return user

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

class AddFeedRequest(BaseModel):
    name: str
    url: str
    category: Optional[str] = None
    freshrss_id: Optional[str] = None

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

TV_TOKEN = "ax-news-tv-readonly-2026"

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/tv/articles")
async def tv_articles(token: str = "", limit: int = 100):
    """Public endpoint for TV dashboard — no session required."""
    if token != TV_TOKEN:
        raise HTTPException(403, "Invalid token")
    rows = await database.get_articles(pool, limit=limit, user_id=1)
    return [serialize_row(r) for r in rows]

@app.post("/api/tv/sync")
async def tv_sync(token: str = "", request: Request = None):
    """Public sync trigger for TV dashboard."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(_sync_attempts, client_ip, 1, 300):
        raise HTTPException(429, "Sync rate limited. Try again in 5 minutes.")
    if token != TV_TOKEN:
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
async def sync_articles():
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
        raise HTTPException(401, "Identifiants invalides")
    if not verify_password(req.password, row["password_hash"]):
        raise HTTPException(401, "Identifiants invalides")
    if not row.get("approved", True):
        raise HTTPException(403, "Your account is pending admin approval.")
    token = await create_session(pool, row["id"])
    response.set_cookie(
        key="ax_session", value=token,
        httponly=True, path="/", max_age=2592000, samesite="lax"
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
        raise HTTPException(409, "Nom d'utilisateur déjà pris")
    ph = hash_password(req.password)
    row = await pool.fetchrow("""
        INSERT INTO users (username, email, password_hash)
        VALUES ($1, $2, $3) RETURNING id, username
    """, req.username, req.email, ph)
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
               COUNT(DISTINCT ur.article_id) AS articles_read,
               COUNT(DISTINCT uk.id)         AS knowledge_count,
               COUNT(DISTINCT uf.id)         AS feeds_count
        FROM users u
        LEFT JOIN user_reads    ur ON ur.user_id = u.id
        LEFT JOIN user_knowledge uk ON uk.user_id = u.id
        LEFT JOIN user_feeds    uf ON uf.user_id = u.id AND uf.active = TRUE
        WHERE u.id = $1
        GROUP BY u.username, u.email
    """, user["id"])
    return serialize_row(dict(row))

@app.post("/api/profile/password")
async def change_password(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    current = body.get("current_password", "")
    new_pw  = body.get("new_password", "")
    if not new_pw or len(new_pw) < 6:
        raise HTTPException(400, "Le nouveau mot de passe doit contenir au moins 6 caractères")
    row = await pool.fetchrow("SELECT password_hash FROM users WHERE id = $1", user["id"])
    if not row or not verify_password(current, row["password_hash"]):
        raise HTTPException(401, "Mot de passe actuel incorrect")
    await pool.execute(
        "UPDATE users SET password_hash = $1 WHERE id = $2",
        hash_password(new_pw), user["id"]
    )
    return {"ok": True}

# ── Articles (authenticated) ──────────────────────────────────────────────────

@app.get("/api/articles")
async def list_articles(
    limit:    int = Query(50, ge=1, le=200),
    offset:   int = Query(0, ge=0),
    category: Optional[str] = None,
    search:   Optional[str] = None,
    user:     dict = Depends(get_current_user),
):
    rows = await database.get_articles(
        pool, limit=limit, offset=offset,
        category=category, search=search, user_id=user["id"]
    )
    return [serialize_row(r) for r in rows]

@app.get("/api/articles/{article_id}")
async def get_article(article_id: int, user: dict = Depends(get_current_user)):
    row = await database.get_article_by_id(pool, article_id, user["id"])
    if not row:
        raise HTTPException(404, "Article introuvable")
    return serialize_row(row)

@app.post("/api/articles/{article_id}/read")
async def mark_read(article_id: int, user: dict = Depends(get_current_user)):
    await database.mark_read(pool, user["id"], article_id)
    return {"ok": True}

@app.get("/api/categories")
async def list_categories(user: dict = Depends(get_current_user)):
    rows = await pool.fetch("""
        SELECT DISTINCT category FROM articles
        WHERE category IS NOT NULL AND category != ''
        ORDER BY category
    """)
    return [r["category"] for r in rows]

# ── Knowledge ─────────────────────────────────────────────────────────────────

@app.get("/api/knowledge")
async def get_knowledge(domain: Optional[str] = None, user: dict = Depends(get_current_user)):
    rows = await database.get_user_knowledge(pool, user_id=user["id"], domain=domain)
    return [serialize_row(r) for r in rows]

@app.get("/api/knowledge/full")
async def get_knowledge_full(user: dict = Depends(get_current_user)):
    rows = await pool.fetch("""
        SELECT uk.id, uk.domain, uk.gap_identified, uk.gap_resolved, uk.created_at,
               a.title AS article_title, a.feed_source AS article_source,
               a.published_at AS article_date
        FROM user_knowledge uk
        LEFT JOIN articles a ON a.id = uk.source_article
        WHERE uk.user_id = $1
        ORDER BY uk.domain, uk.created_at DESC
    """, user["id"])
    grouped: dict = {}
    for r in rows:
        d = r["domain"] or "Général"
        grouped.setdefault(d, []).append({
            "id":              r["id"],
            "gap_identified":  r["gap_identified"],
            "gap_resolved":    r["gap_resolved"],
            "created_at":      r["created_at"].isoformat() if r["created_at"] else None,
            "article_title":   r["article_title"],
            "article_source":  r["article_source"],
            "article_date":    r["article_date"].isoformat() if r["article_date"] else None,
        })
    return grouped

# ── Feeds ─────────────────────────────────────────────────────────────────────

@app.get("/api/feeds")
async def get_feeds(user: dict = Depends(get_current_user)):
    rows = await pool.fetch("""
        SELECT id, freshrss_id, name, url, category, active, added_at
        FROM user_feeds WHERE user_id = $1 ORDER BY name
    """, user["id"])
    if rows:
        return [serialize_row(dict(r)) for r in rows]
    # Default: return distinct feed sources from articles
    src_rows = await pool.fetch("""
        SELECT DISTINCT feed_source AS name, category
        FROM articles WHERE feed_source IS NOT NULL AND feed_source != ''
        ORDER BY feed_source
    """)
    return [{"id": None, "freshrss_id": None, "name": r["name"],
             "url": None, "category": r["category"], "active": True} for r in src_rows]

@app.post("/api/feeds", status_code=201)
async def add_feed(req: AddFeedRequest, user: dict = Depends(get_current_user)):
    fid = req.freshrss_id or req.url
    row = await pool.fetchrow("""
        INSERT INTO user_feeds (user_id, freshrss_id, name, url, category)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, freshrss_id) DO UPDATE SET active = TRUE
        RETURNING id, name
    """, user["id"], fid, req.name, req.url, req.category)
    return dict(row)

@app.delete("/api/feeds/{feed_id}")
async def remove_feed(feed_id: int, user: dict = Depends(get_current_user)):
    result = await pool.execute("""
        UPDATE user_feeds SET active = FALSE
        WHERE id = $1 AND user_id = $2
    """, feed_id, user["id"])
    if result == "UPDATE 0":
        raise HTTPException(404, "Flux introuvable")
    return {"ok": True}

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

Respond in English only. Be concise, structured and insightful. Max 250 words."""

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
        return {"response": reply}
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

# ── Phase 2 additions ─────────────────────────────────────────────────────────

@app.delete("/api/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: int, user: dict = Depends(get_current_user)):
    result = await pool.execute(
        "DELETE FROM user_knowledge WHERE id = $1 AND user_id = $2",
        knowledge_id, user["id"]
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Entry not found")
    return {"ok": True}

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
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        if "access_token" not in token_data:
            raise HTTPException(400, f"Google auth failed: {token_data.get('error', 'unknown')}")
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )
        userinfo = userinfo_resp.json()

    email = userinfo.get("email", "")
    name = userinfo.get("name", "")
    base_username = (name or email.split("@")[0]).replace(" ", "_")[:30]
    username = base_username

    if not email:
        raise HTTPException(400, "No email returned from Google")

    user = await pool.fetchrow("SELECT * FROM users WHERE email = $1", email)

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
        return RedirectResponse("/login.html?pending=1")

    if not user.get("approved"):
        return RedirectResponse("/login.html?pending=1")

    session_token = secrets.token_urlsafe(32)
    await pool.execute("""
        INSERT INTO user_sessions (id, user_id, expires_at)
        VALUES ($1, $2, NOW() + INTERVAL '30 days')
    """, session_token, user["id"])
    nonce = getattr(request.state, 'csp_nonce', secrets.token_urlsafe(16))
    return templates.TemplateResponse(request, "google_callback.html", {
        "csp_nonce": nonce,
        "session_token": session_token,
    })

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
    """Register new user with email verification."""
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

@app.delete("/api/feeds/{feed_id}/permanent")
async def delete_feed_permanent(feed_id: int, user: dict = Depends(get_current_user)):
    result = await pool.execute(
        "DELETE FROM user_feeds WHERE id = $1 AND user_id = $2",
        feed_id, user["id"]
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Feed not found")
    return {"ok": True}

@app.get("/api/categories/tree")
async def categories_tree(user: dict = Depends(get_current_user)):
    rows = await pool.fetch("""
        SELECT category,
               COUNT(*) as total,
               COUNT(CASE WHEN ur.id IS NOT NULL THEN 1 END) as read_count
        FROM articles a
        LEFT JOIN user_reads ur ON ur.article_id = a.id AND ur.user_id = $1
        WHERE a.category IS NOT NULL AND a.category != ''
        GROUP BY a.category
        ORDER BY a.category
    """, user["id"])
    return [{"category": r["category"], "total": r["total"], "read": r["read_count"]} for r in rows]

@app.post("/api/enrich")
async def enrich_articles(limit: int = 500):
    """Static keyword enrichment — fast, no AI calls."""
    count = await enrich_batch_static(pool, limit=limit)
    return {"enriched": count}

@app.get("/api/entities")
async def list_entities(user: dict = Depends(get_current_user)):
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
        GROUP BY e.entity
        ORDER BY article_count DESC
        LIMIT 100
    """)
    return [serialize_row(dict(r)) for r in rows]

@app.get("/api/entities/{entity_name}")
async def entity_detail(entity_name: str, limit: int = 50,
                        user: dict = Depends(get_current_user)):
    """Return articles mentioning a specific entity + sentiment stats."""
    rows = await pool.fetch("""
        SELECT a.id, a.title, a.feed_source, a.category, a.published_at,
               a.url, a.image_url, a.country_code, a.entities,
               a.sentiment, a.sentiment_score,
               (ur.id IS NOT NULL) as is_read
        FROM articles a
        LEFT JOIN user_reads ur ON ur.article_id = a.id AND ur.user_id = $1
        WHERE a.entities @> $2::jsonb
        ORDER BY a.published_at DESC
        LIMIT $3
    """, user["id"], json_lib.dumps([entity_name]), limit)

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
async def list_countries(user: dict = Depends(get_current_user)):
    """Return article counts by country."""
    rows = await pool.fetch("""
        SELECT country_code, COUNT(*) as count
        FROM articles
        WHERE country_code IS NOT NULL AND country_code != ''
        GROUP BY country_code ORDER BY count DESC
    """)
    return [dict(r) for r in rows]

@app.post("/api/translate")
async def trigger_translate(limit: int = 20):
    """Translate up to limit non-English articles."""
    count = await translate_batch(pool, limit=limit)
    return {"translated": count}

@app.get("/api/proxy/ogimage")
async def get_og_image(url: str, token: str = "", request: Request = None):
    """Fetch og:image from a URL server-side to avoid CORS."""
    if not url or not url.startswith("http"):
        raise HTTPException(400, "Invalid URL")
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AXNews/1.0)"}) as client:
            r = await client.get(url)
            html = r.text[:50000]
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
        if m:
            return {"image_url": m.group(1)}
        return {"image_url": None}
    except Exception:
        return {"image_url": None}

@app.post("/api/fetch-images")
async def fetch_missing_images(limit: int = 30):
    """Fetch og:image for articles that have no image_url."""
    rows = await pool.fetch("""
        SELECT id, url FROM articles
        WHERE image_url IS NULL AND url IS NOT NULL AND url != ''
        ORDER BY ingested_at DESC LIMIT $1
    """, limit)
    count = 0
    async with httpx.AsyncClient(timeout=8, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AXNews/1.0)"}) as client:
        for row in rows:
            try:
                r = await client.get(row["url"])
                html = r.text[:30000]
                m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
                if not m:
                    m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
                if m:
                    img_url = m.group(1)
                    if img_url.startswith('http'):
                        await pool.execute(
                            "UPDATE articles SET image_url = $1 WHERE id = $2",
                            img_url, row["id"]
                        )
                        count += 1
            except Exception:
                pass
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
async def purge_old_articles(token: str = ""):
    """Delete articles older than 30 days."""
    TV_TOKEN_VALUE = "ax-news-tv-readonly-2026"
    if token != TV_TOKEN_VALUE:
        raise HTTPException(403, "Not authorized")
    result = await pool.execute("""
        DELETE FROM articles
        WHERE published_at < NOW() - INTERVAL '30 days'
    """)
    deleted = int(result.split()[-1])
    logger.info(f"Purged {deleted} articles older than 30 days")
    return {"deleted": deleted}

@app.get("/api/admin/pending-users")
async def get_pending_users(user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin only")
    rows = await pool.fetch("""
        SELECT id, username, email, created_at, email_verified
        FROM users WHERE approved = false
        ORDER BY created_at DESC
    """)
    return [serialize_row(dict(r)) for r in rows]

@app.post("/api/admin/users/{user_id}/approve")
async def approve_user(user_id: int, user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin only")
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
async def reject_user(user_id: int, user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin only")
    await pool.execute(
        "DELETE FROM users WHERE id = $1 AND is_admin = false", user_id)
    return {"rejected": True}

@app.get("/about")
async def about_page(request: Request):
    """Public landing page for SEO — no auth required."""
    return templates.TemplateResponse(request, "about.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})

# ── HTML page handlers (Jinja2 templates for CSP nonce injection) ─────────────

@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})

@app.get("/login.html", response_class=HTMLResponse)
async def login_html(request: Request):
    return templates.TemplateResponse(request, "login.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})

@app.get("/admin.html", response_class=HTMLResponse)
async def admin_html(request: Request):
    return templates.TemplateResponse(request, "admin.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})

@app.get("/profile.html", response_class=HTMLResponse)
async def profile_html(request: Request):
    return templates.TemplateResponse(request, "profile.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})

@app.get("/tv.html", response_class=HTMLResponse)
async def tv_html(request: Request):
    return templates.TemplateResponse(request, "tv.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})

@app.get("/about.html", response_class=HTMLResponse)
async def about_html(request: Request):
    return templates.TemplateResponse(request, "about.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})

@app.get("/landing.html", response_class=HTMLResponse)
async def landing_html(request: Request):
    return templates.TemplateResponse(request, "landing.html", {"csp_nonce": getattr(request.state, 'csp_nonce', '')})
