"""
Pipeline de génération audio partagé — appelé par l'endpoint on-demand
(main.py) ET par le scruteur automatique (audio-scruteur-worker.py).
pool est passé explicitement pour rester compatible avec les deux contextes
(FastAPI global pool vs pool standalone du worker).
"""
import asyncio
import logging
import wave

import ollama_client

VOICE_MODEL_PATH = "/opt/ax-news/voices/fr_FR-siwis-medium.onnx"
AUDIO_DIR = "/opt/ax-news/audio"
PIPER_BIN = "/opt/ax-news/backend/venv/bin/piper"

logger = logging.getLogger("ax-news.audio")


def get_audio_duration_seconds(wav_path: str) -> int:
    try:
        with wave.open(wav_path, "rb") as w:
            return round(w.getnframes() / w.getframerate())
    except Exception:
        return 0


async def try_lock_audio(pool, article_id: int) -> bool:
    """Atomic lock — returns True only if this caller secured the slot."""
    result = await pool.execute("""
        UPDATE articles SET audio_status = 'generating'
        WHERE id = $1 AND audio_status IN ('none', 'failed')
    """, article_id)
    return result == "UPDATE 1"


async def _audio_done(pool, article_id: int, summary: str, url: str, duration: int):
    await pool.execute("""
        UPDATE articles
        SET audio_status = 'done',
            audio_summary_text = $2,
            audio_url = $3,
            audio_duration_seconds = $4,
            audio_generated_at = NOW(),
            audio_error = NULL
        WHERE id = $1
    """, article_id, summary, url, duration)


async def _audio_failed(pool, article_id: int, error: str):
    await pool.execute("""
        UPDATE articles
        SET audio_status = 'failed', audio_error = $2
        WHERE id = $1
    """, article_id, error[:500])


async def generate_article_audio(pool, article_id: int, content: str) -> bool:
    """
    Génère résumé FR + WAV pour un article.
    Le verrou anti-concurrence est géré par l'appelant via try_lock_audio().
    Retourne True si succès, False si échec (status mis à 'failed' en DB).
    """
    try:
        summary = await ollama_client.summarize_to_french(content)
        output_path = f"{AUDIO_DIR}/{article_id}.wav"
        proc = await asyncio.create_subprocess_exec(
            PIPER_BIN, "--model", VOICE_MODEL_PATH, "--output_file", output_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate(input=summary.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError("piper synthesis failed")
        duration = get_audio_duration_seconds(output_path)
        await _audio_done(pool, article_id, summary, f"/audio/{article_id}.wav", duration)
        logger.info(f"Audio generated for article {article_id}: {duration}s")
        return True
    except ollama_client.OllamaUnavailableError as e:
        await _audio_failed(pool, article_id, str(e))
        logger.warning(f"Audio failed (ollama) for {article_id}: {e}")
        return False
    except Exception as e:
        await _audio_failed(pool, article_id, str(e))
        logger.error(f"Audio error for {article_id}: {e}")
        return False
