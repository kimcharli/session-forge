"""Analysis prompt templates for llama.cpp session analysis."""

SYSTEM_PROMPT = """You are a senior AI engineering analyst. You review AI coding session \
transcripts and identify patterns, inefficiencies, and opportunities to improve prompts, \
system harness, reusable skills, and agent instructions.

Be concrete and actionable. Output a JSON array only — no preamble, no markdown fences."""


def build_analysis_prompt(
    tool: str,
    model: str,
    project_path: str,
    message_count: int,
    transcript: str,
) -> str:
    return f"""Analyze the following AI coding session transcript.

Tool: {tool}
Model: {model}
Project: {project_path}
Turns: {message_count}

Transcript:
{transcript}

Identify up to 5 insights. For each insight return a JSON object with these fields:
- "category": one of ["harness", "skill", "agent", "prompt-pattern"]
- "severity": one of ["suggestion", "warning", "improvement"]
- "summary": one-line description, max 80 characters
- "detail": full markdown explanation with a concrete, actionable recommendation

Return a JSON array of insight objects only. No other text."""
