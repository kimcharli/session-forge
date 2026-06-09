"""llama.cpp HTTP client — calls llama-server OpenAI-compatible API."""

import json
import logging

import httpx

from session_forge.analyzer.prompts import SYSTEM_PROMPT, build_analysis_prompt
from session_forge.config import config

logger = logging.getLogger(__name__)


async def analyze_session(session, messages: list) -> list[dict]:
    """Send session transcript to llama-server and return structured insights."""
    cfg = config().llama
    transcript = _build_transcript(messages)
    user_prompt = build_analysis_prompt(
        tool=session.tool,
        model=session.model or "unknown",
        project_path=session.project_path or "unknown",
        message_count=session.message_count,
        transcript=transcript,
    )

    payload = {
        "model": cfg.model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{cfg.url}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"].strip()
        insights = _parse_insights(raw)
        logger.info(f"Analyzed session {session.id}: {len(insights)} insights")
        return insights

    except Exception as e:
        logger.error(f"Analysis failed for session {session.id}: {e}")
        return []


def _build_transcript(messages: list) -> str:
    lines = [
        f"[{(msg.role if hasattr(msg, 'role') else msg.get('role', '?')).upper()}]\n"
        f"{msg.content if hasattr(msg, 'content') else msg.get('content', '')}\n"
        for msg in messages
    ]
    return "\n---\n".join(lines)


def _parse_insights(raw: str) -> list[dict]:
    """Parse JSON array from LLM response, stripping markdown fences if present."""
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(clean)
    except Exception as e:
        logger.warning(f"Failed to parse insights JSON: {e}\nRaw: {raw[:200]}")
        return []
