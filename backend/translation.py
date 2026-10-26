"""
Offline translation into English (the site's language) with Argos Translate:
no rate limit, no API key, no network. A story is translated when its source
is known to be in another language (feed_catalog.lang, user_feeds.lang, set
on articles.original_lang at ingestion) or when its title is in a CJK
script. Its title and its first paragraphs are translated; the full original
stays in original_content, and the reader links to it.
"""
import asyncio, html as html_lib, logging, re, time, unicodedata
from concurrent.futures import ThreadPoolExecutor

LEAD_CHARS = 1500   # the excerpt and the reader's first paragraphs


def needs_translation(title: str, lang: str | None = None) -> bool:
    """lang: the source's language when it is known."""
    if lang and lang.lower().split("-")[0] not in ("en", ""):
        return True
    if not title:
        return False
    for c in title:
        if unicodedata.east_asian_width(c) in ('W', 'F'):
            return True
    return False

logger = logging.getLogger("ax-news")
_executor = ThreadPoolExecutor(max_workers=1)

NON_ENGLISH = {
    'ko', 'ja', 'zh-cn', 'zh-tw', 'zh', 'fr', 'de', 'es', 'pt',
    'ar', 'ru', 'it', 'nl', 'pl', 'sv', 'fi', 'da', 'no', 'tr',
    'vi', 'th', 'id', 'ms', 'hi', 'bn', 'ur', 'fa'
}

# Map langdetect and catalog codes to Argos codes (Argos says "nb" for
# Norwegian, "zh" for Chinese); any other code is the same in both.
LANG_MAP = {
    'zh-cn': 'zh', 'zh-tw': 'zh', 'zh': 'zh',
    'zh_cn': 'zh', 'zh_tw': 'zh',  # extra variants
    'no': 'nb', 'iw': 'he',
}

def _script_language(text: str) -> str | None:
    """The language a CJK script says, before langdetect guesses: it reads a
    Chinese title mixed with Latin words (product names, "AI") as Korean or
    German, and Argos then translates from the wrong language."""
    if re.search(r'[\uac00-\ud7af\u1100-\u11ff]', text):
        return 'ko'
    if re.search(r'[\u3040-\u30ff]', text):
        return 'ja'
    if re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', text):
        return 'zh'
    return None

def _detect_language(text: str) -> str:
    script = _script_language(text or '')
    if script:
        return script
    try:
        from langdetect import detect
        if not text or len(text.strip()) < 10:
            return 'en'
        return detect(text.strip()[:500])
    except Exception:
        return 'en'

def _translate_with_argos(text: str, from_code: str) -> str | None:
    """Translate text using Argos Translate offline engine."""
    try:
        import argostranslate.translate
        argos_from = LANG_MAP.get(from_code, from_code)
        result = argostranslate.translate.translate(text[:2000], argos_from, 'en')
        if result and result != text:
            return result
        return None
    except Exception as e:
        logger.warning(f"Argos translation error ({from_code}): {e}")
        return None

def _translate_text(text: str, source_lang: str, max_chars: int = 4000) -> str:
    """Translate text offline using Argos. No rate limits."""
    if not text or not text.strip():
        return text

    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()[:max_chars]

    result = _translate_with_argos(clean, source_lang)
    if result:
        return result

    logger.warning(f"Translation failed for lang={source_lang}, returning original")
    return text

async def translate_article(article: dict) -> dict | None:
    title = article.get("title", "") or ""
    content = article.get("content_raw", "") or ""
    detect_text = title if len(title) > 10 else (content[:500] if content else title)

    loop = asyncio.get_event_loop()
    lang = await loop.run_in_executor(_executor, _detect_language, detect_text)

    if lang not in NON_ENGLISH:
        return None

    argos_lang = LANG_MAP.get(lang, lang)
    try:
        import argostranslate.translate
        installed = [l.code for l in argostranslate.translate.get_installed_languages()]
        if argos_lang not in installed:
            logger.warning(f"Argos language not installed: {argos_lang}")
            return None
    except Exception:
        return None

    logger.info(f"Translating [{lang}] via Argos: {title[:60]}")

    translated_title = await loop.run_in_executor(
        _executor, _translate_text, title, lang)

    clean_content = re.sub(r'<[^>]+>', ' ', content)
    clean_content = re.sub(r'\s+', ' ', clean_content).strip()
    translated_content = ""
    if clean_content:
        translated_content = await loop.run_in_executor(
            _executor, _translate_text, clean_content[:6000], lang)

    return {
        "original_lang": lang,
        "original_title": title,
        "original_content": content,
        "translated_title": translated_title,
        "translated_content": translated_content,
    }

def _lead(html: str, limit: int = LEAD_CHARS) -> list[str]:
    """An article's first paragraphs, as plain text, up to about limit characters."""
    from db import paragraphs
    out, n = [], 0
    for p in paragraphs(html or ""):
        if out and n + len(p) > limit:
            break
        out.append(p[:limit])
        n += len(p)
    return out


def _installed() -> set:
    try:
        import argostranslate.translate
        return {l.code for l in argostranslate.translate.get_installed_languages()}
    except Exception:
        return set()


def _translate_story(title: str, content: str, lang: str) -> tuple[str, str] | None:
    """(English title, English lead as HTML paragraphs), or None if Argos
    gave nothing back."""
    new_title = _translate_with_argos(title, lang) if title else ""
    if title and not new_title:
        return None
    parts = []
    for p in _lead(content):
        t = _translate_with_argos(p, lang)
        parts.append(t or p)
    return new_title, "".join(f"<p>{html_lib.escape(p)}</p>" for p in parts)


async def translate_batch(pool, limit: int = 200, budget: float | None = None) -> int:
    """Translate pending articles, newest first: one claim of `limit`, or,
    with a budget in seconds, claims of 20 until the time is spent."""
    loop = asyncio.get_event_loop()
    installed = await loop.run_in_executor(_executor, _installed)
    deadline = time.monotonic() + budget if budget else None
    count = 0
    while True:
        rows = await pool.fetch("""
            UPDATE articles
            SET translation_status = 'in_progress'
            WHERE id IN (
                SELECT id FROM articles
                WHERE translation_status = 'pending'
                ORDER BY published_at DESC
                LIMIT $1
            )
            RETURNING id, title, content_raw, original_lang
        """, 20 if deadline else limit)
        if not rows:
            break
        for row in rows:
            if deadline and time.monotonic() > deadline:
                # Out of time: what is left goes back to the queue.
                await pool.execute("UPDATE articles SET translation_status = 'pending' WHERE id = $1", row["id"])
                continue
            try:
                count += await _translate_row(pool, loop, row, installed)
            except Exception as e:
                logger.error(f"Translation error for id={row['id']}: {e}")
                await pool.execute(
                    "UPDATE articles SET translation_status = 'failed' WHERE id = $1", row["id"])
        if not deadline or time.monotonic() > deadline:
            break
    return count


async def _translate_row(pool, loop, row, installed) -> int:
    title, content = row["title"] or "", row["content_raw"] or ""
    hint = (row["original_lang"] or "").lower()
    if hint in ("", "en"):
        if not needs_translation(title):
            # English article mis-classified as pending — mark done immediately
            await pool.execute("""
                UPDATE articles SET translation_status = 'done', translated_at = NOW(), original_lang = 'en'
                WHERE id = $1""", row["id"])
            return 0
        hint = await loop.run_in_executor(_executor, _detect_language, title if len(title) > 10 else content[:500])
    lang = LANG_MAP.get(hint, hint)
    if lang == "en":
        await pool.execute("""
            UPDATE articles SET translation_status = 'done', translated_at = NOW(), original_lang = 'en'
            WHERE id = $1""", row["id"])
        return 0
    if lang not in installed:
        # No model for this language: the story waits, out of sight, until
        # deploy/install-argos-models.sh installs one (and the admin requeues).
        await pool.execute("""
            UPDATE articles SET translation_status = 'failed', original_lang = $2 WHERE id = $1""",
            row["id"], lang)
        return 0
    result = await loop.run_in_executor(_executor, _translate_story, title, content, lang)
    new_title = (result or ("", ""))[0]
    cjk = sum(1 for c in new_title[:20] if unicodedata.east_asian_width(c) in ('W', 'F'))
    if not result or not new_title.strip() or cjk > 3:
        # Argos returned the original script, or a loop of it:
        # failed, not pending, or the same articles would be
        # retried on every run and the queue would never move.
        await pool.execute(
            "UPDATE articles SET translation_status = 'failed', original_lang = $2 WHERE id = $1", row["id"], lang)
        return 0
    await pool.execute("""
        UPDATE articles
        SET title              = $1,
            content_raw        = $2,
            original_lang      = $3,
            original_title     = $4,
            original_content   = $5,
            translated_at      = NOW(),
            translation_status = 'done'
        WHERE id = $6
    """, new_title[:500], result[1] or content, lang, title, content, row["id"])
    logger.info(f"[{lang}→en] {new_title[:60]}")
    return 1
