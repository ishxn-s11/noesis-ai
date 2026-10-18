"""Agent framework: typed specs, evidence rules, optional LLM drafting.

Every agent is a registered AgentSpec with a system prompt, permitted tools,
memory access policy, and typed output. Execution is deterministic tool-driven
code; an optional OpenAI-compatible LLM (NOESIS_LLM_BASE_URL / _API_KEY) may
draft narrative fields, but tool results and numerical outputs always come
from executed code — an agent can never claim work it did not perform
(the graph rejects nodes that produce no evidence).
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel


class AgentResult(BaseModel):
    """Typed output of one agent node."""

    summary: str
    output: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []  # tool invocations + artifact/check references


@dataclass(frozen=True)
class AgentSpec:
    name: str
    display_name: str
    role: str
    system_prompt: str
    tools: tuple[str, ...]
    memory_policy: str  # e.g. "read:semantic,episodic;write:episodic"
    max_retries: int = 2


def evidence(tool: str, *, args: dict | None = None, result_summary: str = "",
             artifact_ids: list[str] | None = None, check_names: list[str] | None = None,
             duration_s: float | None = None) -> dict:
    """Build one evidence record proving a tool actually ran."""
    return {
        "tool": tool,
        "args": args or {},
        "result_summary": result_summary[:600],
        "artifact_ids": artifact_ids or [],
        "check_names": check_names or [],
        "duration_s": duration_s,
        "at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


class LLMClient:
    """Optional OpenAI-compatible chat completion client (never required)."""

    def __init__(self) -> None:
        from app.core.config import settings

        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def draft(self, system: str, prompt: str, max_tokens: int = 1200) -> str | None:
        """Draft narrative text. Returns None in offline/deterministic mode."""
        if not self.available:
            return None
        try:
            import httpx

            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return None


llm = LLMClient()
