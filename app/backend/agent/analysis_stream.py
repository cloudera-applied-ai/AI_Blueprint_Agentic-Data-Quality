"""Single-turn LLM streaming for analysis (no tool-calling loop).

Yields SSE-shaped dicts: content / done / error events.
Reuses chat_completion_stream from agent/llm_client.py.
"""

from typing import AsyncGenerator

from openai import OpenAI

from agent.llm_client import chat_completion_stream


async def stream_analysis(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_content: str,
) -> AsyncGenerator[dict, None]:
    """Stream a single-turn LLM completion as SSE events.

    Yields:
        {"event": "content", "data": {"text": "<accumulated text>"}}
        {"event": "done",    "data": {}}
        {"event": "error",   "data": {"message": "..."}}
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        stream = chat_completion_stream(client, model, messages)
        full_text = ""

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_text += delta.content
                yield {"event": "content", "data": {"text": full_text}}

        yield {"event": "done", "data": {}}

    except Exception as e:
        yield {"event": "error", "data": {"message": str(e)[:500]}}
