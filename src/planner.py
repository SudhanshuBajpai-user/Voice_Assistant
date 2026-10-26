import re


ACTION_START = (
    r"open|launch|start|run|search|look up|google|"
    r"check|show|tell me|find|make a note|take a note|"
    r"set a timer|set a reminder|create|play|pause|"
    r"next track|increase|decrease|mute|unmute|"
    r"go to|visit"
)

SPLIT_PATTERN = re.compile(
    rf"\s+and(?:\s+then)?\s+(?=(?:{ACTION_START})\b)",
    re.IGNORECASE,
)

SEARCH_PATTERN = re.compile(
    r"^(?:"
    r"search(?:\s+(?:the\s+web|the\s+internet|online))?\s+for"
    r"|look\s+up|google"
    r")\s+(.+)$",
    re.IGNORECASE,
)


def normalize_step(step: str) -> str:
    """Normalize planner fragments for the existing intent classifier."""
    step = step.strip(" \t,.;!?")
    match = SEARCH_PATTERN.match(step)

    if match:
        query = match.group(1).strip(" \t,.;!?")
        if query:
            return f"search the web for {query}"

    return step


def plan_command(command: str) -> list[str]:
    """Split a compound request into ordered, normalized steps."""
    text = re.sub(r"\s+", " ", (command or "")).strip()

    if not text:
        return []

    raw_steps = [
        part.strip(" \t,.;!?")
        for part in SPLIT_PATTERN.split(text)
        if part.strip(" \t,.;!?")
    ]

    # If Whisper dropped "open" before Edge, infer it only when
    # the next step is clearly a web-search request.
    if len(raw_steps) > 1:
        first = raw_steps[0].lower()
        next_step = normalize_step(raw_steps[1]).lower()

        if (
            first in {"edge", "microsoft edge"}
            and next_step.startswith("search the web for ")
        ):
            raw_steps[0] = "open Edge"

    return [normalize_step(step) for step in raw_steps]