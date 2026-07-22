"""
Scruteur audio automatique — traite les articles récents (fenêtre 48h)
sans audio généré. Réutilise backend/audio_pipeline.py — pas de logique
dupliquée avec l'endpoint on-demand.
Batch capé à 15 par cycle pour ne pas saturer Ollama .37 ni la RAM lab05.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, '/opt/ax-news/backend')

venv_site = '/opt/ax-news/backend/venv/lib/python3.12/site-packages'
if venv_site not in sys.path:
    sys.path.insert(0, venv_site)

from dotenv import load_dotenv
load_dotenv('/opt/ax-news/backend/.env')

import asyncpg

from audio_pipeline import generate_article_audio, try_lock_audio
import db

DATABASE_URL = os.getenv('DATABASE_URL')
BATCH_SIZE = 15
WINDOW_HOURS = 48

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger('audio-scruteur')


async def run():
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    try:
        candidates = await db.get_articles_needing_audio(pool, WINDOW_HOURS, BATCH_SIZE)

        if not candidates:
            logger.info("Aucun article éligible ce cycle.")
            return

        logger.info(f"{len(candidates)} article(s) éligible(s) dans la fenêtre {WINDOW_HOURS}h")
        ok_count = 0
        fail_count = 0

        for article in candidates:
            locked = await try_lock_audio(pool, article['id'])
            if not locked:
                logger.info(f"article {article['id']}: déjà verrouillé (on-demand concurrent ?)")
                continue
            ok = await generate_article_audio(pool, article['id'], article['content_raw'])
            if ok:
                ok_count += 1
                logger.info(f"article {article['id']}: ok")
            else:
                fail_count += 1
                logger.warning(f"article {article['id']}: failed")

        logger.info(f"Cycle terminé — {ok_count} ok, {fail_count} failed")
    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(run())
