"""Claude through the Claude Agent SDK, with the studio tools served as an in-process MCP server.

The SDK needs ANTHROPIC_API_KEY (Anthropic does not allow third-party products to use the claude.ai
sign-in). The key is read from the environment or the per-user providers.json; it never enters the
repository. The SDK is asyncio-based, so the client lives on a private event loop thread and
`run_turn` is synchronous for the interface.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Callable

from studio_assistant.tools import SYSTEM_PROMPT, TOOL_SPECS, call_tool

SERVER_NAME = "studio"


class AgentSDKAssistant:
    def __init__(self, settings: dict):
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, create_sdk_mcp_server, tool

        api_key = settings.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("Claude via the Agent SDK needs an Anthropic API key (ANTHROPIC_API_KEY or the provider settings)")
        self.settings = settings
        self._on_event: Callable[[str, dict], None] = lambda kind, payload: None
        tools = []
        for spec in TOOL_SPECS:
            tools.append(self._make_tool(tool, spec))
        server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=tools)
        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            mcp_servers={SERVER_NAME: server},
            allowed_tools=[f"mcp__{SERVER_NAME}__{spec['name']}" for spec in TOOL_SPECS],
            tools=[],                          # no built-in file or shell tools: the studio tools only
            permission_mode="dontAsk",
            include_partial_messages=True,
            max_turns=24,
            setting_sources=[],
            env={"ANTHROPIC_API_KEY": api_key},
            **({"model": settings["model"]} if settings.get("model") else {}),
        )
        self.model = settings.get("model") or "default"
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="agent-sdk-loop", daemon=True)
        self.thread.start()
        self.client = ClaudeSDKClient(options=options)
        self._run(self.client.connect())

    def _make_tool(self, tool, spec: dict):
        assistant = self

        @tool(spec["name"], spec["description"], spec["parameters"])
        async def handler(args: dict) -> dict:
            assistant._on_event("tool_call", {"name": spec["name"], "arguments": args})
            result = call_tool(spec["name"], args)
            assistant._on_event("tool_result", {"name": spec["name"], "result": result})
            return {"content": [{"type": "text", "text": json.dumps(result)}], "is_error": "error" in result}
        return handler

    def _run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def run_turn(self, user_text: str, on_event: Callable[[str, dict], None]) -> str:
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
        from claude_agent_sdk.types import StreamEvent
        self._on_event = on_event

        async def turn():
            await self.client.query(user_text)
            final = ""
            streamed = False
            async for message in self.client.receive_response():
                if isinstance(message, StreamEvent):
                    event = message.event
                    if event.get("type") == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                        streamed = True
                        on_event("text", {"delta": event["delta"]["text"]})
                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            final = block.text
                            if not streamed:
                                on_event("text", {"delta": block.text})
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        on_event("error", {"message": message.result or message.subtype})
                    final = final or (message.result or "")
            return final

        try:
            final = self._run(turn())
        except Exception as error:
            on_event("error", {"message": str(error)})
            final = ""
        on_event("done", {"text": final})
        return final

    def close(self):
        try:
            self._run(self.client.disconnect())
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
