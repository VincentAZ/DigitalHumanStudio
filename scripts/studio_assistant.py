#!/usr/bin/env python3
"""Terminal entry point for the director's assistant (same tools and providers as the control center).

usage: studio_assistant.py [--provider anthropic|openai|google|xai|openrouter] [--model M] [message ...]
Without a message it reads turns from standard input. Transcripts go to artifacts/assistant/.
Run through the interface environment: .runtime/studio-app/bin/python -m studio_assistant ... or scripts/studio.sh --assistant.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_assistant import TRANSCRIPTS  # noqa: E402
from studio_assistant.providers import PROVIDERS, key_status, make_assistant, provider_settings  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=list(PROVIDERS), default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument("message", nargs="*")
    args = parser.parse_args()
    print(f"provider: {PROVIDERS[args.provider]['title']} ({key_status(args.provider)})", file=sys.stderr)
    assistant = make_assistant(args.provider)
    if args.model:
        assistant.model = args.model
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = TRANSCRIPTS / f"{stamp}-{args.provider}"
    folder.mkdir(parents=True, exist_ok=True)
    transcript = (folder / "transcript.jsonl").open("a")

    def on_event(kind, payload):
        transcript.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(), "kind": kind, **payload}) + "\n")
        transcript.flush()
        if kind == "text":
            print(payload["delta"], end="", flush=True)
        elif kind == "tool_call":
            print(f"\n  → {payload['name']}({json.dumps(payload['arguments'])})", file=sys.stderr)
        elif kind == "tool_result":
            print(f"  ← {json.dumps(payload['result'])[:300]}", file=sys.stderr)
        elif kind == "error":
            print(f"\n[error] {payload['message']}", file=sys.stderr)
        elif kind == "done":
            print()

    turns = [" ".join(args.message)] if args.message else iter(lambda: input("you> "), "")
    try:
        for turn in turns:
            if not turn.strip():
                continue
            transcript.write(json.dumps({"t": dt.datetime.now(dt.timezone.utc).isoformat(), "kind": "user", "text": turn}) + "\n")
            assistant.run_turn(turn, on_event)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        if hasattr(assistant, "close"):
            assistant.close()
        print(f"transcript: {folder / 'transcript.jsonl'}", file=sys.stderr)


if __name__ == "__main__":
    main()
