#!/usr/bin/env python3
"""Standalone translation worker — runs outside uvicorn to avoid OOM crashes."""
import asyncio, asyncpg, os, logging, sys
os.environ['HOME'] = '/opt/ax-news/.argos-home'

# To standard output only: ax-news-translate.service appends it to
# /var/log/ax-news/translate.log (a FileHandler as well wrote every line twice).
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger('translate-worker')

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://ax_news:@localhost/ax_news')

async def main():
    sys.path.insert(0, '/opt/ax-news/backend')
    # Activate venv
    venv_site = '/opt/ax-news/backend/venv/lib/python3.12/site-packages'
    if venv_site not in sys.path:
        sys.path.insert(0, venv_site)

    from translation import translate_batch
    # Argos logs every hypothesis at INFO: about 100 MB of log a day.
    import argostranslate.utils
    logging.getLogger('argostranslate.utils').setLevel(logging.WARNING)
    pool = await asyncpg.create_pool(DATABASE_URL)
    try:
        # A run cut short (MemoryMax, a restart) leaves its batch marked
        # in_progress for ever; runs never overlap (a oneshot unit), so any
        # left at the start of one go back to the queue.
        await pool.execute(
            "UPDATE articles SET translation_status = 'pending' WHERE translation_status = 'in_progress'")
        count = await translate_batch(pool, limit=30)
        logger.info(f'Translated: {count}')
        # Stats
        row = await pool.fetchrow(
            "SELECT COUNT(*) FILTER (WHERE translation_status='pending') as pending,"
            "COUNT(*) FILTER (WHERE translation_status='done') as done,"
            "COUNT(*) FILTER (WHERE translation_status='failed') as failed FROM articles")
        logger.info(f"Pending: {row['pending']}, Done: {row['done']}, Failed: {row['failed']}")
    finally:
        await pool.close()

if __name__ == '__main__':
    asyncio.run(main())
