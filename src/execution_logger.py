"""Append privacy-conscious execution events to a JSON Lines history file."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

LOG_FILE = (
    Path(__file__).resolve().parent.parent
    / "logs"
    / "execution_history.jsonl"
)

# These intents may contain user-provided content in the utterance.
# Keep the event and status, but don't persist the argument text.
REDACT_COMMAND_INTENTS = {
    "SEARCH_WEB",
    "MAKE_NOTES",
    "SET_TIMER",
    "SET_REMINDER",
    "CREATE_FOLDER",
    "CREATE_TEXT_FILE",
    "RUN_PYTHON_SCRIPT",
    "OPEN_WEBSITE",
}


def log_event(
    command: str = "",
    intent: Optional[str] = None,
    confidence: Optional[float] = None,
    status: str = "unknown",
    message: Optional[str] = None,
    action_outcome: Optional[dict] = None,
) -> None:
    """Append an event; logging failures must never crash the agent."""
    intent_text = intent.strip().upper() if isinstance(intent, str) else None

    if intent_text in REDACT_COMMAND_INTENTS:
        safe_command = "[argument-bearing command redacted]"
    else:
        safe_command = (command or "")[:200]

    safe_outcome = None
    if action_outcome is not None:
        safe_outcome = {
            "intent": action_outcome.get("intent"),
            "success": action_outcome.get("success"),
            "status": action_outcome.get("status"),
            "message": (action_outcome.get("message") or "")[:300],
        }

    event = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "intent": intent_text,
        "confidence": round(float(confidence), 4) if confidence is not None else None,
        "status": status,
        "message": (message or "")[:300] if message else None,
        "command": safe_command,
        "action_outcome": safe_outcome,
        "error_message": (
            safe_outcome.get("message")
            if safe_outcome
            and safe_outcome.get("status") in {"failed", "exception"}
            else None
        ),
    }

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        # The voice agent should remain usable even if logging is unavailable.
        print(f"Warning: execution log unavailable: {exc}")
