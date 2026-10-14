"""OpenAI-compatible LLM client wrapper for Cloudera AI Inference / Ollama."""

import httpx
from openai import OpenAI

from net import ssl_context


def create_client(base_url: str, api_key: str, timeout: float = 30.0) -> OpenAI:
    # Trust the system store too: Private Cloud CAII certs are signed by the cluster CA.
    http_client = httpx.Client(verify=ssl_context(), timeout=timeout)
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, http_client=http_client)


def test_connection(base_url: str, api_key: str, model: str) -> dict:
    """Test LLM connectivity. Returns {"ok": True/False, "message": str}."""
    try:
        client = create_client(base_url, api_key, timeout=10.0)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=10,
        )
        text = response.choices[0].message.content or ""
        return {"ok": True, "message": f"Connected. Response: {text.strip()[:50]}"}
    except Exception as e:
        return {"ok": False, "message": str(e)[:200]}


def chat_completion(
    client: OpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
) -> object:
    """Non-streaming chat completion with optional tools."""
    kwargs = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def chat_completion_stream(
    client: OpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
):
    """Streaming chat completion. Yields chunks."""
    kwargs = {"model": model, "messages": messages, "stream": True}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)
