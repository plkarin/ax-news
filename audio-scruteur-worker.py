"""
Scruteur audio automatique — traite systématiquement tous les articles
sans audio (status 'none' ou 'failed'), les plus récents en premier.
Découplé du sync RSS — timer séparé, même isolation que translate-standalone.py.
Batch capé par run pour ne pas saturer Ollama .37 : le plafond limite le
débit par cycle, pas le périmètre (tout finit par passer, cycle après cycle).
"""
import asyncio
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
BATCH_SIZE = 25


async def run():
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    try:
        candidates = await db.get_articles_needing_audio(pool, BATCH_SIZE)

        if not candidates:
            print("Aucun article en attente ce cycle.")
            return

        print(f"{len(candidates)} article(s) en attente")
        ok_count = 0
        fail_count = 0

        for article in candidates:
            locked = await try_lock_audio(pool, article['id'])
            if not locked:
                print(f"article {article['id']}: skip (verrou concurrent)")
                continue
            ok = await generate_article_audio(pool, article['id'], article['content_raw'])
            if ok:
                ok_count += 1
                print(f"article {article['id']}: ok")
            else:
                fail_count += 1
                print(f"article {article['id']}: failed")

        print(f"Cycle terminé — {ok_count} ok, {fail_count} failed")
    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(run())
