"""
Client HTTP pour Ollama hébergé sur ax bare-metal (.37).
Utilisé exclusivement pour : résumé d'article en français, style oral court.
Aucune autre tâche ne doit transiter par ce client — garder le modèle
dédié à une charge légère et prévisible.
"""
import httpx

OLLAMA_URL = "http://192.168.1.37:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b-instruct"
OLLAMA_TIMEOUT = 30  # secondes — au-delà, considérer .37 indisponible

SUMMARY_PROMPT_TEMPLATE = """Résume l'article suivant en français, entre 100 et 130 mots.
Style oral, adapté à une lecture à voix haute (synthèse vocale).

Interdiction stricte : ne commence jamais par "cet article", "cette étude",
"les auteurs présentent" ou toute formule qui nomme l'article lui-même.
Commence directement par le sujet traité, comme si tu racontais l'info à l'oral.

Si tu mentionnes un nom propre d'algorithme, d'outil ou de logiciel technique
peu connu du grand public, ajoute aussitôt une très courte précision sur ce
qu'il fait ou le domaine qu'il concerne — l'auditeur ne peut pas chercher le
terme, contrairement à un lecteur. Exemple : pas "avec Tamarin prover" mais
"avec Tamarin, un outil de vérification de protocoles cryptographiques".
Reste bref sur ces précisions, une poignée de mots suffit, ne transforme pas
le résumé en glossaire.

Pas de markdown, pas de liste, texte continu uniquement.

Article :
{content}
"""


class OllamaUnavailableError(Exception):
    pass


async def summarize_to_french(content: str) -> str:
    prompt = SUMMARY_PROMPT_TEMPLATE.format(content=content[:6000])
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.4}
            })
            resp.raise_for_status()
            return resp.json()["response"].strip()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise OllamaUnavailableError(f"Ollama .37 injoignable: {e}")
