"""Generate a Markdown chat archive from local Codex session logs.

The script extracts visible user/assistant messages from the newest local
Codex session JSONL file and writes them to chat_history.md.
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path


SKIP_PREFIXES = (
    "<environment_context>",
    "# AGENTS.md instructions",
)


def sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


def message_text(payload: dict) -> str:
    parts: list[str] = []
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"input_text", "output_text", "text"}:
            text = item.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def session_summary(path: Path) -> tuple[str, int]:
    latest_timestamp = ""
    message_count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = message_text(payload)
            if not text or text.startswith(SKIP_PREFIXES):
                continue
            message_count += 1
            timestamp = record.get("timestamp") or ""
            if timestamp > latest_timestamp:
                latest_timestamp = timestamp
    return latest_timestamp, message_count


def session_contains_text(path: Path, needle: str) -> bool:
    needle_lower = needle.lower()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue
            text = message_text(payload)
            if needle_lower in text.lower():
                return True
    return False


def newest_session(prefer_cwd: bool = True) -> Path:
    candidates: list[tuple[str, int, Path]] = []
    for path in sessions_root().rglob("*.jsonl"):
        latest_timestamp, message_count = session_summary(path)
        if message_count:
            candidates.append((latest_timestamp, message_count, path))
    if not candidates:
        raise FileNotFoundError(f"No Codex session JSONL files found under {sessions_root()}")
    if prefer_cwd:
        cwd = str(Path.cwd())
        cwd_candidates = [item for item in candidates if session_contains_text(item[2], cwd)]
        if cwd_candidates:
            cwd_candidates.sort(key=lambda item: (item[0], item[1], str(item[2])))
            return cwd_candidates[-1][2]
    candidates.sort(key=lambda item: (item[0], item[1], str(item[2])))
    return candidates[-1][2]


def extract_messages(path: Path) -> list[dict]:
    messages: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            text = message_text(payload)
            if not text or text.startswith(SKIP_PREFIXES):
                continue
            messages.append(
                {
                    "timestamp": record.get("timestamp") or "",
                    "role": role,
                    "text": text,
                }
            )
    return messages


def render_markdown(messages: list[dict], source: Path) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = [
        "# Chat History",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Source session: `{source}`",
        "- Scope: visible user/assistant messages extracted from local Codex session logs.",
        "- Excluded: system/developer instructions, tool calls, tool outputs, and hidden reasoning.",
        "",
    ]
    for index, message in enumerate(messages, start=1):
        role = "User" if message["role"] == "user" else "Assistant"
        timestamp = message["timestamp"]
        escaped = html.escape(message["text"], quote=False)
        lines.extend(
            [
                f"## {index:04d} — {timestamp} — {role}",
                "",
                "<pre>",
                escaped,
                "</pre>",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("chat_history.md"))
    parser.add_argument("--any-session", action="store_true", help="Do not prefer sessions mentioning the current working directory.")
    args = parser.parse_args()

    source = args.session if args.session else newest_session(prefer_cwd=not args.any_session)
    messages = extract_messages(source)
    args.output.write_text(render_markdown(messages, source), encoding="utf-8")
    print(f"Wrote {len(messages)} messages to {args.output} from {source}")


if __name__ == "__main__":
    main()
