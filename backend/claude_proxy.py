import asyncio, json, re, logging

logger = logging.getLogger("ax-news")

async def call_claude(system_prompt: str, messages: list,
                      user_message: str, claude_user="cbrain") -> tuple[str, dict | None]:
    history = ""
    for m in messages:
        role = "Pierre" if m["role"] == "user" else "Assistant"
        history += f"\n\n{role}: {m['content']}"

    full_prompt = f"""{system_prompt}

--- HISTORIQUE ---
{history if history else "(premiere question)"}

--- QUESTION ---
Pierre: {user_message}

Reponds directement en francais. A la fin de ta reponse, si tu identifies une lacune de connaissance
comblée, ajoute un bloc JSON sur une ligne separee avec ce format exact:
KNOWLEDGE_UPDATE: {{"domain": "...", "gap_identified": "...", "gap_resolved": "..."}}
"""

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=full_prompt.encode("utf-8")), timeout=120
        )
        response = stdout.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            logger.error(f"Claude subprocess error: {err}")
            return f"Erreur Claude: {err[:200]}", None

        knowledge = None
        ku_match = re.search(r"KNOWLEDGE_UPDATE:\s*(\{.+\})", response)
        if ku_match:
            try:
                knowledge = json.loads(ku_match.group(1))
                response = response[:ku_match.start()].strip()
            except json.JSONDecodeError:
                pass

        return response, knowledge

    except asyncio.TimeoutError:
        logger.error("Claude subprocess timed out")
        return "Erreur: délai d'attente dépassé (120s)", None
    except Exception as e:
        logger.exception("Claude subprocess unexpected error")
        return f"Erreur inattendue: {str(e)}", None
