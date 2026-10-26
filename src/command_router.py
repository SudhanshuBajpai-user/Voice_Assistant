
import re

from entity_extractor import extract_arguments


CLARIFICATION_MESSAGES = {
    "SEARCH_WEB": "What would you like me to search for?",
    "MAKE_NOTES": "What would you like me to write in the note?",
    "SET_TIMER": "How long should I set the timer for?",
}


def normalize_text(command: str) -> str:
    return re.sub(r"\s+", " ", command or "").strip().lower()


def has_search_request(text: str) -> bool:
    patterns = [
        r"\bsearch\s+(?:(?:the\s+)?(?:web|internet|online)\s+)?for\s+\S+",
        r"\blook\s+up\s+\S+",
        r"\blook\s+.+?\s+up(?:\s+for me)?\b",
        r"\bfind\s+.+?\s+(?:online|on the web|on the internet)\b",
        r"\bgoogle\s+\S+",
    ]

    return any(re.search(pattern, text) for pattern in patterns)


def validate_command_intent(intent: str, command: str):
    """Validate that the transcript supports the predicted action."""
    text = normalize_text(command)

    if not text:
        return False, "I didn't receive a usable command. Please try again."
        # Reject unusually repetitive speech transcripts.
    words = text.split()

    if len(words) >= 20 and len(set(words)) / len(words) < 0.45:
        return (
            False,
            "The transcript sounded repetitive or unclear. Please try again.",
        )
    # Never start Jupyter when the user asks to close it.
    if intent == "START_JUPYTER" and re.search(
        r"\b(close|stop|shut down|quit|kill|terminate|exit)\b",
        text,
    ):
        return (
            False,
            "Closing Jupyter is not supported yet. "
            "I won't start another server.",
        )

    # Prevent unrelated actions when a web search was requested.
    if intent != "SEARCH_WEB" and has_search_request(text):
        return (
            False,
            "I heard a web-search request, but the predicted action "
            "doesn't match. Please repeat your command.",
        )

    action_words = (
        r"\b(?:open|launch|start|run|bring|pull|get|load|"
        r"switch|need|want)\b"
    )

    if intent == "OPEN_EDGE":
        has_target = bool(
            re.search(r"\b(?:microsoft\s+)?edge\b|\bbrowser\b", text)
        )
        has_action = bool(re.search(action_words, text))

        if not (has_target and has_action):
            return False, "Please clearly ask me to open Edge."

    elif intent == "OPEN_NOTEPAD":
        has_target = bool(re.search(r"\bnotepad\b", text))
        has_action = bool(re.search(action_words, text))

        if not (has_target and has_action):
            return False, "Please clearly ask me to open Notepad."

    elif intent == "OPEN_VSCODE":
        has_target = bool(
            re.search(
                r"\bvisual studio code\b|"
                r"\bvs\s*code\b|"
                r"\bcode editor\b|"
                r"\bprogramming editor\b|"
                r"\bcoding editor\b|"
                r"\bcoding\b|"
                r"\bwrite code\b",
                text,
            )
        )
        has_action = bool(re.search(action_words, text))

        if not (has_target and has_action):
            return False, "Please explicitly mention opening VS Code."

    elif intent == "OPEN_PROJECT":
        has_target = bool(
            re.search(r"\bproject\b|\bworkspace\b|\brepository\b|\brepo\b", text)
        )
        has_action = bool(re.search(action_words, text))

        if not (has_target and has_action):
            return False, "Please clearly identify the project to open."

    elif intent == "SCREENSHOT":
        has_target = bool(
            re.search(
                r"\bscreenshot\b|"
                r"\bscreen\s+capture\b|"
                r"\bcapture\s+(?:my\s+)?screen\b|"
                r"\bprint\s+screen\b|"
                r"\btake\s+(?:a\s+)?screen\s*shot\b",
                text,
            )
        )

        if not has_target:
            return False, "Please explicitly ask for a screenshot."

    elif intent == "STOP_ASSISTANT":
        explicit_stop = bool(
            re.search(
                r"\bstop\s+(?:the\s+)?"
                r"(?:assistant|voice assistant|voice agent|listening)\b|"
                r"\bquit\s+(?:listening|the assistant|the voice agent)\b|"
                r"\bend\s+(?:voice mode|the session|the assistant session)\b|"
                r"\bterminate\s+(?:the\s+)?"
                r"(?:session|assistant|voice agent)\b|"
                r"\bexit\s+(?:the\s+)?"
                r"(?:assistant|voice assistant)\b|"
                r"\bclose\s+(?:the\s+)?"
                r"(?:assistant|voice assistant)\b",
                text,
            )
        )

        simple_stop_text = re.sub(r"[,.;!?]+", " ", text)
        simple_stop_text = re.sub(r"\s+", " ", simple_stop_text).strip()

        short_stop = bool(
            re.fullmatch(
                r"(?:and\s+)?(?:please\s+)?"
                r"stop(?:\s+stop){0,4}(?:\s+please)?",
                simple_stop_text,
            )
        )

        if not (explicit_stop or short_stop):
            return (
                False,
                "Please use a clear stop command, such as 'stop listening'.",
            )

    return True, None


def prepare_command(intent: str, command: str) -> dict:
    """
    Validate the predicted intent, extract its arguments,
    and decide whether the command is ready to execute.
    """
    intent = (intent or "").strip().upper()
    text = (command or "").strip()

    if intent == "UNKNOWN":
        return {
            "status": "not_actionable",
            "intent": intent,
            "command": text,
            "arguments": {},
            "message": "I couldn't identify a supported action.",
        }

    valid, message = validate_command_intent(intent, text)

    if not valid:
        return {
            "status": "needs_clarification",
            "intent": intent,
            "command": text,
            "arguments": {},
            "message": message,
        }

    arguments = extract_arguments(intent, text)
    
    if arguments.get("needs_clarification", False):
        return {
            "status": "needs_clarification",
            "intent": intent,
            "command": text,
            "arguments": arguments,
            "message": CLARIFICATION_MESSAGES.get(
                intent,
                "Could you provide more information?",
            ),
        }

    return {
        "status": "ready",
        "intent": intent,
        "command": text,
        "arguments": arguments,
        "message": None,
    }
