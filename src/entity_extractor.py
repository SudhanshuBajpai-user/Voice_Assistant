
import re


def clean_text(text: str) -> str:
    """Normalize whitespace and trim surrounding punctuation."""
    return re.sub(r"\s+", " ", text).strip(
        " \t\r\n.,!?;:"
    )


# --------------------------------------------------
# 1. SEARCH_WEB: extract the search query
# --------------------------------------------------

def extract_search_query(command: str) -> dict:
    text = command.strip()

    # Remove common polite prefixes.
    text = re.sub(
        r"^please\s+",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^(?:can|could|would)\s+you\s+",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^please\s+",
        "",
        text,
        flags=re.IGNORECASE
    )

    query = text

    # Handle: "look this up for me"
    match = re.match(
        r"^look\s+(.+?)\s+up(?:\s+for me)?$",
        text,
        flags=re.IGNORECASE
    )

    if match:
        query = match.group(1)

    else:
        prefixes = [
            r"^search\s+(?:(?:the\s+)?"
            r"(?:web|internet|online)\s+)?"
            r"(?:for\s+)?",

            r"^look\s+up\s+",

            r"^look\s+for\s+",

            r"^find\s+"
            r"(?:(?:information|details|results)\s+"
            r"(?:about|on)\s+)?",

            r"^google\s+",

            r"^i\s+(?:need|want)\s+"
            r"(?:some\s+)?information\s+about\s+",
        ]

        for pattern in prefixes:
            updated, count = re.subn(
                pattern,
                "",
                query,
                count=1,
                flags=re.IGNORECASE
            )

            if count:
                query = updated
                break

    # Remove trailing phrases that describe the search method.
    query = re.sub(
        r"\s+(?:online|on the web|on the internet)$",
        "",
        query,
        flags=re.IGNORECASE
    )

    query = re.sub(
        r"\s+for me$",
        "",
        query,
        flags=re.IGNORECASE
    )

    query = clean_text(query)

    # These expressions do not specify a useful search target.
    vague_queries = {
        "this",
        "that",
        "it",
        "something",
        "this thing",
        "that thing",
    }

    needs_clarification = (
        not query
        or query.casefold() in vague_queries
    )

    return {
        "query": query or None,
        "needs_clarification": needs_clarification,
    }


# --------------------------------------------------
# 2. MAKE_NOTES: extract note content
# --------------------------------------------------

def extract_note_content(command: str) -> dict:
    text = command.strip()

    # A colon explicitly marks the content to record.
    # Example: "write this down: buy a keyboard"
    if ":" in text:
        content = clean_text(text.split(":", 1)[1])

        return {
            "content": content or None,
            "needs_clarification": not bool(content),
        }

    patterns = [
        r"^(?:please\s+)?"
        r"(?:make|create|take|save)\s+"
        r"(?:a\s+)?note\s+"
        r"(?:saying|that says|about|to|that)\s+(.+)$",

        r"^(?:please\s+)?"
        r"note\s+that\s+(.+)$",

        r"^(?:please\s+)?"
        r"write\s+down\s+(.+)$",
    ]

    content = None

    for pattern in patterns:
        match = re.match(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            content = clean_text(match.group(1))
            break

    # Remove generic phrases that aren't actual note content.
    if content and content.casefold() in {
        "this",
        "that",
        "this for later",
        "for later",
    }:
        content = None

    return {
        "content": content or None,
        "needs_clarification": not bool(content),
    }


# --------------------------------------------------
# 3. SET_TIMER: extract duration
# --------------------------------------------------

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def extract_timer_duration(command: str) -> dict:
    number_pattern = (
        r"\d+(?:\.\d+)?|"
        + "|".join(NUMBER_WORDS.keys())
    )

    pattern = (
        rf"\b(?P<number>{number_pattern})\s*"
        r"(?P<unit>seconds?|secs?|"
        r"minutes?|mins?|hours?|hrs?)\b"
    )

    match = re.search(
        pattern,
        command,
        flags=re.IGNORECASE
    )

    if not match:
        return {
            "duration_seconds": None,
            "needs_clarification": True,
        }

    number_text = match.group("number").casefold()
    unit = match.group("unit").casefold()

    if number_text in NUMBER_WORDS:
        number = NUMBER_WORDS[number_text]
    else:
        number = float(number_text)

    if unit.startswith("s"):
        multiplier = 1
    elif unit.startswith("m"):
        multiplier = 60
    else:
        multiplier = 3600

    duration_seconds = number * multiplier

    # Reject zero or negative-effective durations.
    if duration_seconds <= 0:
        return {
            "duration_seconds": None,
            "needs_clarification": True,
        }

    return {
        "duration_seconds": int(duration_seconds),
        "needs_clarification": False,
    }


# --------------------------------------------------
# Public interface used by the voice assistant
# --------------------------------------------------

def extract_arguments(intent: str, command: str) -> dict:
    """
    Extract arguments required for a predicted intent.

    This function does not execute any PC actions.
    """

    if intent == "SEARCH_WEB":
        return extract_search_query(command)

    if intent == "MAKE_NOTES":
        return extract_note_content(command)

    if intent == "SET_TIMER":
        return extract_timer_duration(command)

    # Intents that need no arguments return an empty dictionary.
    return {}
