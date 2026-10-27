"""Provider adapters. Each exposes `run_turn(user_text, on_event)` and keeps its own conversation.

Events delivered to `on_event(kind, payload)`:
  text      {"delta": str}                streamed assistant text
  tool_call {"name": str, "arguments": dict}
  tool_result {"name": str, "result": dict}
  done      {"text": str}                 the turn's final assistant text
  error     {"message": str}
Keys never live in the repository: they come from the environment or from
~/.config/digital-human-studio/providers.json (written by the interface with mode 0600).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Optional

from studio_assistant.tools import SYSTEM_PROMPT, TOOL_SPECS, call_tool

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "digital-human-studio" / "providers.json"

PROVIDERS = {
    "anthropic": {"title": "Claude (Agent SDK, your Claude Code sign-in)", "kind": "agent_sdk", "model": "", "env": "ANTHROPIC_API_KEY"},
    "openai": {"title": "OpenAI", "kind": "openai_compatible", "base_url": "https://api.openai.com/v1", "model": "gpt-5", "env": "OPENAI_API_KEY"},
    "google": {"title": "Google Gemini", "kind": "openai_compatible", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-pro", "env": "GEMINI_API_KEY"},
    "xai": {"title": "xAI Grok", "kind": "openai_compatible", "base_url": "https://api.x.ai/v1", "model": "grok-4", "env": "XAI_API_KEY"},
    "openrouter": {"title": "OpenRouter", "kind": "openai_compatible", "base_url": "https://openrouter.ai/api/v1", "model": "anthropic/claude-sonnet-4.5", "env": "OPENROUTER_API_KEY"},
}


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, ValueError):
        return {}


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    os.chmod(CONFIG_PATH, 0o600)


def provider_settings(name: str) -> dict:
    base = dict(PROVIDERS[name])
    stored = load_config().get(name, {})
    base.update({k: v for k, v in stored.items() if v})
    if not base.get("api_key"):
        base["api_key"] = os.environ.get(base.get("env", ""), "")
    return base


def key_status(name: str) -> str:
    settings = provider_settings(name)
    if settings["kind"] == "agent_sdk":
        return "uses the Claude Code sign-in (or ANTHROPIC_API_KEY if set)"
    return "key set" if settings.get("api_key") else f"no key: set {settings['env']} or enter one"


class OpenAICompatibleAssistant:
    """Chat Completions with function tools, streamed; works for OpenAI, Gemini, xAI and OpenRouter."""

    def __init__(self, name: str):
        from openai import OpenAI
        self.settings = provider_settings(name)
        if not self.settings.get("api_key"):
            raise RuntimeError(f"no API key for {self.settings['title']}")
        self.client = OpenAI(base_url=self.settings["base_url"], api_key=self.settings["api_key"])
        self.model = self.settings["model"]
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in TOOL_SPECS]

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self.client.models.list())

    def run_turn(self, user_text: str, on_event: Callable[[str, dict], None], max_steps: int = 12) -> str:
        self.messages.append({"role": "user", "content": user_text})
        final = ""
        for _ in range(max_steps):
            stream = self.client.chat.completions.create(model=self.model, messages=self.messages, tools=self.tools, stream=True)
            text, calls = "", {}
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    text += delta.content
                    on_event("text", {"delta": delta.content})
                for call in delta.tool_calls or []:
                    slot = calls.setdefault(call.index, {"id": call.id or "", "name": "", "arguments": ""})
                    if call.id:
                        slot["id"] = call.id
                    if call.function and call.function.name:
                        slot["name"] += call.function.name
                    if call.function and call.function.arguments:
                        slot["arguments"] += call.function.arguments
            if not calls:
                self.messages.append({"role": "assistant", "content": text})
                final = text
                break
            self.messages.append({"role": "assistant", "content": text or None,
                                  "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in calls.values()]})
            for c in calls.values():
                try:
                    arguments = json.loads(c["arguments"] or "{}")
                except ValueError:
                    arguments = {}
                on_event("tool_call", {"name": c["name"], "arguments": arguments})
                result = call_tool(c["name"], arguments)
                on_event("tool_result", {"name": c["name"], "result": result})
                self.messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})
        on_event("done", {"text": final})
        return final


def make_assistant(name: str):
    settings = provider_settings(name)
    if settings["kind"] == "agent_sdk":
        from studio_assistant.anthropic_provider import AgentSDKAssistant
        return AgentSDKAssistant(settings)
    return OpenAICompatibleAssistant(name)
