"""
Offline translation using Argos Translate.
No rate limits, no API keys, no internet required.
Supports: ko, zh, ja, vi, fr, de, es, pt, ar, ru, it, nl, tr -> en
"""
import asyncio, logging, re, unicodedata
from concurrent.futures import ThreadPoolExecutor

def needs_translation(title: str) -> bool:
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

# Map langdetect codes to argos codes
LANG_MAP = {
    'zh-cn': 'zh', 'zh-tw': 'zh', 'zh': 'zh',
    'zh_cn': 'zh', 'zh_tw': 'zh',  # extra variants
    'ko': 'ko', 'ja': 'ja', 'vi': 'vi',
    'fr': 'fr', 'de': 'de', 'es': 'es', 'pt': 'pt',
    'ar': 'ar', 'ru': 'ru', 'it': 'it', 'nl': 'nl', 'tr': 'tr',
}

def _detect_language(text: str) -> str:
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

async def translate_batch(pool, limit: int = 200) -> int:
    """
    Translate pending articles using Argos offline engine.
    Uses translation_status flag to track state reliably.
    """
    # Mark a batch as in_progress atomically
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
    """, limit)

    count = 0
    for row in rows:
        if not needs_translation(row['title']):
            # English article mis-classified as pending — mark done immediately
            await pool.execute("""
                UPDATE articles
                SET translation_status = 'done',
                    translated_at = NOW(),
                    original_lang = 'en'
                WHERE id = $1
            """, row['id'])
            continue
        try:
            result = await translate_article(dict(row))
            if result and result["original_lang"] in NON_ENGLISH:
                new_title = result["translated_title"] or ""
                cjk = sum(1 for c in new_title[:20]
                          if unicodedata.east_asian_width(c) in ('W', 'F'))
                if cjk > 3:
                    # Translation failed — back to pending
                    await pool.execute(
                        "UPDATE articles SET translation_status = 'pending' WHERE id = $1",
                        row["id"])
                    continue
                # Success
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
                """,
                    new_title,
                    result["translated_content"] or row["content_raw"],
                    result["original_lang"],
                    result["original_title"],
                    result["original_content"],
                    row["id"])
                count += 1
                logger.info(f"[{result['original_lang']}→en] {new_title[:60]}")
            else:
                # English article — mark done
                await pool.execute("""
                    UPDATE articles
                    SET translated_at      = NOW(),
                        original_lang      = 'en',
                        translation_status = 'done'
                    WHERE id = $1
                """, row["id"])
        except Exception as e:
            logger.error(f"Translation error for id={row['id']}: {e}")
            await pool.execute(
                "UPDATE articles SET translation_status = 'pending' WHERE id = $1",
                row["id"])

    return count
