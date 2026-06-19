#!/usr/bin/env python3
"""Standalone translation worker — runs outside uvicorn to avoid OOM crashes."""
import asyncio, asyncpg, os, logging, sys
os.environ['HOME'] = '/opt/ax-news/.argos-home'

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('/var/log/ax-news/translate.log'),
              logging.StreamHandler()])
logger = logging.getLogger('translate-worker')

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://ax_news:@localhost/ax_news')

async def main():
    sys.path.insert(0, '/opt/ax-news/backend')
    # Activate venv
    venv_site = '/opt/ax-news/backend/venv/lib/python3.12/site-packages'
    if venv_site not in sys.path:
        sys.path.insert(0, venv_site)

    from translation import translate_batch
    pool = await asyncpg.create_pool(DATABASE_URL)
    try:
        count = await translate_batch(pool, limit=30)
        logger.info(f'Translated: {count}')
        # Stats
        row = await pool.fetchrow(
            "SELECT COUNT(*) FILTER (WHERE translation_status='pending') as pending,"
            "COUNT(*) FILTER (WHERE translation_status='done') as done FROM articles")
        logger.info(f"Pending: {row['pending']}, Done: {row['done']}")
    finally:
        await pool.close()

if __name__ == '__main__':
    asyncio.run(main())
