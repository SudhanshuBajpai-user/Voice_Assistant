"""Small in-memory session state for the voice assistant's pending request."""

from typing import Optional, TypedDict


class PendingCommand(TypedDict):
    intent: str
    command: str


class SessionController:
    """Owns temporary state required to complete multi-turn requests."""

    def __init__(self) -> None:
        self._pending_command: Optional[PendingCommand] = None

    def has_pending(self) -> bool:
        return self._pending_command is not None

    def get_pending(self) -> Optional[PendingCommand]:
        if self._pending_command is None:
            return None
        return self._pending_command.copy()

    def set_pending(self, intent: str, command: str) -> None:
        self._pending_command = {
            "intent": intent.strip().upper(),
            "command": command,
        }

    def clear_pending(self) -> None:
        self._pending_command = None
