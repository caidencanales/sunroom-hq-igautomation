"""Thin wrappers around the Claude API."""
import anthropic

from config import MODEL

client = anthropic.Anthropic()


def parse(output_cls, system, user, effort="low", max_tokens=6000):
    """Structured output: returns an instance of output_cls, or None if the model declined."""
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": user}],
        output_format=output_cls,
    )
    if resp.stop_reason == "refusal":
        return None
    return resp.parsed_output


def web_search(prompt, max_uses=5):
    """Let Claude search the web and return its final text answer."""
    messages = [{"role": "user", "content": prompt}]
    for _ in range(4):  # the server-side search loop can pause; resend to resume
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            output_config={"effort": "low"},
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}],
            messages=messages,
        )
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    return "\n".join(b.text for b in resp.content if b.type == "text")
