import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from planner import plan_command
from session_controller import SessionController
import torch
import whisper
from tensorflow import keras
from execution_logger import log_event
from response import report_action_result, report_plan_summary

from action import execute_intent, get_last_action_outcome
from command_router import prepare_command
from entity_extractor import extract_arguments
# ============================================================
# 1. PROJECT PATHS
# ============================================================

session = SessionController()


def log_execution_event(
    command="",
    intent=None,
    confidence=None,
    status="unknown",
    message=None,
    action_outcome=None,
):
    """Write an execution event without allowing logging to break the agent."""
    try:
        log_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status=status,
            message=message,
            action_outcome=action_outcome,
        )
    except Exception as exc:
        print(f"Warning: execution log could not be written: {exc}")


def report_rejected_action(intent, message, status="rejected"):
    outcome = {
        "intent": intent,
        "success": False,
        "status": status,
        "message": message,
    }
    report_action_result(intent or "command", outcome)
    return outcome


PROJECT_PATH = Path(
    "/home/sudhanshu_bajpai/projects/Voice_assistant"
)

SRC_PATH = PROJECT_PATH / "data"
AUDIO_PATH = PROJECT_PATH / "audio"

AUDIO_PATH.mkdir(exist_ok=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

MODEL_PATH = DATA_DIR / "intent_model_lstm_v4.keras"
METADATA_PATH = DATA_DIR / "intent_metadata_lstm.json"
AUDIO_FILE = AUDIO_PATH / "command.wav"


# ============================================================
# 2. SETTINGS
# ============================================================

# Whisper
WHISPER_MODEL_NAME = "base.en"

# Microphone
SAMPLE_RATE = 16000
DURATION = 5
CHANNELS = 1

# Your working WSL microphone
AUDIO_DEVICE = 4

# General confidence threshold
CONFIDENCE_THRESHOLD = 0.70

# Stop command gets a stricter threshold
STOP_CONFIDENCE_THRESHOLD = 0.90


# ============================================================
# 3. IMPORT ACTION SYSTEM AND COMMAND ROUTER
# ============================================================

action_file = next(
    PROJECT_PATH.rglob("action.py"),
    None
)

if action_file is None:
    raise FileNotFoundError(
        f"Could not find action.py under {PROJECT_PATH}"
    )

# Make both the action module and src modules importable.
module_dirs = [
    PROJECT_PATH / "src",
    action_file.parent,
]

for module_dir in module_dirs:
    if module_dir.exists() and str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))


# ============================================================
# 4. LOAD INTENT MODEL
# ============================================================

print("Loading TensorFlow intent model...")

intent_model = keras.models.load_model(
    MODEL_PATH
)

with open(METADATA_PATH, "r", encoding="utf-8") as f:
    metadata = json.load(f)

vocab = metadata["vocab"]

id_to_intent = metadata["id_to_intent"]
intents = [
    id_to_intent[str(i)]
    for i in range(len(id_to_intent))
]

MAX_LEN = metadata["max_len"]

print("Intent model loaded.")
print("Available intents:")

for intent in intents:
    print(" -", intent)


# ============================================================
# 5. LOAD WHISPER
# ============================================================

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print()
print("Whisper device:", DEVICE)

if DEVICE == "cuda":
    print(
        "GPU:",
        torch.cuda.get_device_name(0)
    )

print("Loading Whisper...")

whisper_model = whisper.load_model(
    WHISPER_MODEL_NAME,
    device=DEVICE
)

print("Whisper loaded.")


# ============================================================
# 6. TEXT TOKENIZATION
# ============================================================

def tokenize(text):
    """
    Convert text into lowercase word tokens.
    """

    return re.findall(
        r"[a-zA-Z0-9']+",
        text.lower()
    )


# ============================================================
# 7. TEXT ENCODING
# ============================================================

def encode_sentence(sentence):
    """
    Convert a sentence into the same integer representation
    used during TensorFlow model training.
    """

    tokens = tokenize(sentence)

    ids = []

    for token in tokens:

        word_id = vocab.get(
            token,
            vocab["<UNK>"]
        )

        ids.append(word_id)

    # Truncate
    ids = ids[:MAX_LEN]

    # Padding
    while len(ids) < MAX_LEN:
        ids.append(
            vocab["<PAD>"]
        )

    return np.array(
        [ids],
        dtype=np.int32
    )


# ============================================================
# 8. COMMAND NORMALIZATION
# ============================================================

def normalize_command(text):
    """
    Small normalization layer for common Whisper mistakes.
    This is intentionally limited.
    """

    text = text.lower().strip()

    replacements = {
        "open edgy": "open edge",
        "open edgey": "open edge",
        "open microsoft edgy": "open microsoft edge",
        "openedgy": "open edge",
        "edge kholo": "open edge"
    }

    for wrong, correct in replacements.items():

        text = text.replace(
            wrong,
            correct
        )

    return text


# ============================================================
# 9. PREDICT INTENT
# ============================================================

def predict_intent(command):

    x = encode_sentence(command)

    probabilities = intent_model.predict(
        x,
        verbose=0
    )[0]

    prediction = int(
        np.argmax(probabilities)
    )

    confidence = float(
        probabilities[prediction]
    )

    intent = intents[prediction]

    return intent, confidence, probabilities


# ============================================================
# 10. RECORD MICROPHONE
# ============================================================

def record_command():

    SAMPLE_RATE = 16000
    CHANNELS = 1
    DEVICE = 4

    BLOCK_SIZE = 1024

    START_THRESHOLD = 500
    SILENCE_THRESHOLD = 350

    REQUIRED_SPEECH_BLOCKS = 3
    SILENCE_BLOCKS_TO_STOP = 12

    MAX_RECORDING_SECONDS = 8
    MIN_RECORDING_SECONDS = 0.5

    frames = []

    speech_started = False
    speech_blocks = 0
    silence_blocks = 0

    start_time = None

    print("\n🎤 Waiting for speech...")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        device=DEVICE,
        blocksize=BLOCK_SIZE
    ) as stream:

        while True:

            data, overflowed = stream.read(BLOCK_SIZE)

            if overflowed:
                print("Warning: audio overflow")

            data = data.copy()

            # Calculate signal energy
            rms = np.sqrt(
                np.mean(
                    data.astype(np.float32) ** 2
                )
            )

            # ------------------------------------------------
            # WAITING FOR SPEECH
            # ------------------------------------------------

            if not speech_started:

                if rms > START_THRESHOLD:

                    speech_blocks += 1

                else:

                    speech_blocks = 0

                if speech_blocks >= REQUIRED_SPEECH_BLOCKS:

                    speech_started = True
                    start_time = time.time()

                    print("🗣️ Speech detected...")

                    frames.append(data)

                continue

            # ------------------------------------------------
            # RECORDING SPEECH
            # ------------------------------------------------

            frames.append(data)

            elapsed = time.time() - start_time

            if rms < SILENCE_THRESHOLD:

                silence_blocks += 1

            else:

                silence_blocks = 0

            # Stop after enough silence
            if silence_blocks >= SILENCE_BLOCKS_TO_STOP:

                if elapsed >= MIN_RECORDING_SECONDS:
                    break

            # Safety timeout
            if elapsed >= MAX_RECORDING_SECONDS:

                print("Maximum recording time reached.")
                break

    if not frames:

        print("No speech detected.")

        return None

    audio = np.concatenate(
        frames,
        axis=0
    )

    write(
        AUDIO_FILE,
        SAMPLE_RATE,
        audio
    )

    duration = len(audio) / SAMPLE_RATE

    print(
        f"Recording finished ({duration:.2f}s)."
    )

    return AUDIO_FILE


# ============================================================
# 11. TRANSCRIBE AUDIO
# ============================================================

def transcribe_audio(audio_file):

    print("Transcribing...")

    try:
        result = whisper_model.transcribe(
            str(audio_file),
            language="en",
            task="transcribe",
            fp16=(DEVICE == "cuda"),
            temperature=0,
            condition_on_previous_text=False,
            initial_prompt=(
                "This is a computer voice command. "
                "Commands include open Edge, open VS Code, "
                "open Notepad, check CPU, check GPU, "
                "start Jupyter, search the web, make a note, "
                "and stop listening."
            )
        )

    except Exception as e:
        print("Whisper error:", e)
        return ""

    return result["text"].strip()


# ============================================================
# 12. PROCESS ONE VOICE COMMAND
# ============================================================

def process_planned_step(step):
    """Classify, validate, execute, and log one planned step.

    Return values are for pipeline control and include the action outcome:
      {"control": True, ...}  -> step dispatched; continue the sequence
      {"control": False, ...} -> the agent should stop
      {"control": None, ...}  -> step failed; pause the sequence
      None/False              -> step was rejected or stop was accepted
    """
    command = normalize_command(step).strip(" \t.,!?;:")

    try:
        intent, confidence, _ = predict_intent(command)
    except Exception as exc:
        print(f"Intent prediction failed: {exc}")
        log_execution_event(
            command=step,
            intent=None,
            confidence=None,
            status="prediction_error",
            message=str(exc),
        )
        return None

    print(f"Intent: {intent}")
    print(f"Confidence: {confidence:.2%}")

    if confidence < CONFIDENCE_THRESHOLD:
        message = "I'm not confident enough to execute that command."
        print(message)
        report_rejected_action(intent, message, "rejected_low_confidence")
        log_execution_event(
            command=step,
            intent=intent,
            confidence=confidence,
            status="rejected_low_confidence",
            message=message,
        )
        return None

    if intent == "STOP_ASSISTANT":
        if confidence < STOP_CONFIDENCE_THRESHOLD:
            message = "I need a clearer stop command."
            print(message)
            report_rejected_action(intent, message, "rejected_stop_low_confidence")
            log_execution_event(
                command=step,
                intent=intent,
                confidence=confidence,
                status="rejected_stop_low_confidence",
                message=message,
            )
            return None

        log_execution_event(
            command=step,
            intent=intent,
            confidence=confidence,
            status="stop_requested",
            message="Explicit stop intent accepted.",
        )
        return False

    try:
        prepared = prepare_command(intent, command)
    except Exception as exc:
        print(f"Command routing failed: {exc}")
        report_rejected_action(intent, str(exc), "router_error")
        log_execution_event(
            command=step,
            intent=intent,
            confidence=confidence,
            status="router_error",
            message=str(exc),
        )
        return None

    status = prepared["status"]
    if status != "ready":
        message = prepared.get("message") or "Step was not ready to execute."
        print(message)
        report_rejected_action(intent, message, status)
        log_execution_event(
            command=step,
            intent=intent,
            confidence=confidence,
            status=status,
            message=message,
        )
        return None

    arguments = prepared.get("arguments", {})
    if arguments:
        print("Extracted arguments:", arguments)

    print("Executing...")
    try:
        loop_result = execute_intent(intent, command, arguments=arguments)
    except Exception as exc:
        print("Action error:", exc)
        log_execution_event(
            command=step,
            intent=intent,
            confidence=confidence,
            status="action_error",
            message=str(exc),
        )
        return None

    outcome = get_last_action_outcome() or {
        "intent": intent,
        "success": None,
        "status": "dispatched_unverified",
        "message": "Action result was unavailable.",
    }
    report_action_result(intent, outcome)

    if loop_result is False:
        log_execution_event(
            command=step,
            intent=intent,
            confidence=confidence,
            status="stop_requested",
            message=outcome.get("message"),
            action_outcome=outcome,
        )
        return {"control": False, "outcome": outcome}

    log_execution_event(
        command=step,
        intent=intent,
        confidence=confidence,
        status=outcome.get("status", "dispatched"),
        message=outcome.get("message"),
        action_outcome=outcome,
    )
    if outcome.get("success") is False:
        return {"control": None, "outcome": outcome}
    return {"control": True, "outcome": outcome}


def process_voice_command():

    audio_file = record_command()
    if audio_file is None:
        log_execution_event(
            status="no_audio",
            message="No speech recording was captured.",
        )
        return True

    transcript = transcribe_audio(audio_file)
    if not transcript:
        print("I couldn't understand the command.")
        log_execution_event(
            status="transcription_failed",
            message="Transcription returned no text.",
        )
        return True

    original_command = transcript.strip()
    command = normalize_command(original_command)
    clean_command = command.strip(" \t.,!?;:").lower()

    print()
    print(f"🗣️ You said: {original_command}")
    if command != original_command:
        print(f"Normalized: {command}")

    # Planning happens before whole-utterance classification.
    steps = plan_command(command)
    if len(steps) > 1:
        print(f"Planned {len(steps)} steps:")
        plan_outcomes = []
        for i, step in enumerate(steps, start=1):
            print(f"  {i}. {step}")

        # Do not persist the raw compound utterance; individual steps are logged.
        log_execution_event(
            command="[compound request]",
            status="planned",
            message=f"Planner produced {len(steps)} steps.",
        )

        for i, step in enumerate(steps, start=1):
            print(f"\n--- Step {i}/{len(steps)} ---")
            step_result = process_planned_step(step)
            if isinstance(step_result, dict):
                result = step_result["control"]
                step_outcome = step_result["outcome"]
            else:
                result = step_result
                step_outcome = {
                    "intent": None,
                    "success": None,
                    "status": "rejected",
                    "message": "Step was rejected or not dispatched.",
                }
                report_action_result(step, step_outcome)
            plan_outcomes.append(step_outcome)

            if result is None:
                print("Sequence paused because this step was rejected or not dispatched.")
                log_execution_event(
                    command="[compound request]",
                    intent=step_outcome.get("intent"),
                    status="sequence_paused",
                    message=step_outcome.get("message")
                    or f"Step {i}/{len(steps)} was not dispatched.",
                    action_outcome=step_outcome,
                )
                report_plan_summary(plan_outcomes)
                return True
            if result is False:
                log_execution_event(
                    command="[compound request]",
                    intent=step_outcome.get("intent"),
                    status="sequence_stopped",
                    message=step_outcome.get("message")
                    or f"Agent stopped at step {i}/{len(steps)}.",
                    action_outcome=step_outcome,
                )
                report_plan_summary(plan_outcomes)
                return False

        log_execution_event(
            command="[compound request]",
            status="sequence_dispatched",
            message=f"All {len(steps)} steps were dispatched; completion was not independently verified.",
        )
        report_plan_summary(plan_outcomes)
        return True

    cancel_phrases = {
        "cancel", "cancel that", "never mind", "nevermind", "forget it",
    }

    explicit_stop = bool(re.fullmatch(
        r"(?:please\s+)?(?:stop listening(?: now)?|"
        r"stop (?:the )?(?:assistant|voice assistant|voice agent)|"
        r"quit listening|exit assistant)[.!]?",
        clean_command,
    ))

    explicit_new_command_patterns = [
        r"(?:please\s+)?(?:open|launch|start|run)\s+"
        r"(?:microsoft\s+)?(?:edge|vs code|visual studio code|notepad|"
        r"jupyter|python|calculator|file explorer|terminal|powershell|"
        r"command prompt|task manager|snipping tool|youtube|github)(?:\s+please)?",
        r"(?:please\s+)?(?:check|show|display)(?:\s+me)?\s+(?:my\s+)?"
        r"(?:cpu|processor(?: usage)?|gpu|ram|memory|system status)(?:\s+please)?",
        r"(?:please\s+)?(?:make|write|take)\s+(?:me\s+)?(?:a\s+)?note",
        r"(?:please\s+)?set\s+(?:a\s+)?timer",
        r"(?:please\s+)?(?:search the web|search online|search the internet|google|look up)",
        r"(?:please\s+)?(?:pause|resume) listening",
    ]
    explicit_new_command = any(
        re.fullmatch(pattern, clean_command)
        for pattern in explicit_new_command_patterns
    )

    if session.has_pending():
        waiting_intent = session.get_pending()["intent"]

        if clean_command in cancel_phrases:
            session.clear_pending()
            print("Pending request cancelled.")
            log_execution_event(
                command=clean_command,
                intent=waiting_intent,
                status="pending_cancelled",
                message="User cancelled the pending request.",
            )
            return True

        if explicit_stop:
            session.clear_pending()
            log_execution_event(
                command="[pending request]",
                intent=waiting_intent,
                status="pending_cancelled_for_stop",
                message="Pending request cleared for explicit stop command.",
            )

        elif explicit_new_command:
            print("Starting a new command; the previous pending request was cancelled.")
            session.clear_pending()
            log_execution_event(
                command="[pending request]",
                intent=waiting_intent,
                status="pending_replaced",
                message="A new command replaced the pending request.",
            )

        else:
            words = re.findall(r"[a-zA-Z0-9']+", original_command.lower())
            if len(words) >= 20 and len(set(words)) / len(words) < 0.45:
                message = "That sounded repetitive or unclear. Please repeat your answer."
                print(message)
                log_execution_event(
                    command=original_command,
                    intent=waiting_intent,
                    status="pending_answer_rejected",
                    message=message,
                )
                return True

            if waiting_intent == "MAKE_NOTES":
                arguments = {
                    "content": original_command,
                    "needs_clarification": not bool(original_command.strip()),
                }
            else:
                arguments = extract_arguments(waiting_intent, original_command)

            if arguments.get("needs_clarification", False):
                prompts = {
                    "SET_TIMER": "How long should I set the timer for?",
                    "MAKE_NOTES": "What would you like me to write?",
                    "SEARCH_WEB": "What would you like me to search for?",
                }
                message = prompts.get(waiting_intent, "Please provide more information.")
                print(message)
                log_execution_event(
                    command="[pending answer]",
                    intent=waiting_intent,
                    status="pending_clarification",
                    message=message,
                )
                return True

            arguments.pop("needs_clarification", None)
            pending_original_command = session.get_pending()["command"]
            session.clear_pending()
            print(f"Follow-up received for {waiting_intent}.")
            print("Extracted arguments:", arguments)
            print("Executing...")
            try:
                loop_result = execute_intent(
                    waiting_intent,
                    pending_original_command,
                    arguments=arguments,
                )
            except Exception as exc:
                print("Action error:", exc)
                log_execution_event(
                    command=original_command,
                    intent=waiting_intent,
                    status="action_error",
                    message=str(exc),
                )
                return True

            if loop_result is False:
                outcome = get_last_action_outcome() or {
                    "intent": waiting_intent,
                    "success": True,
                    "status": "stop_requested",
                    "message": "Dispatcher requested agent shutdown.",
                }
                report_action_result(waiting_intent, outcome)
                log_execution_event(
                    command="[pending request]",
                    intent=waiting_intent,
                    status="stop_requested",
                    message=outcome.get("message"),
                    action_outcome=outcome,
                )
                return False

            outcome = get_last_action_outcome() or {
                "intent": waiting_intent,
                "success": None,
                "status": "dispatched_unverified",
                "message": "Action result was unavailable.",
            }
            report_action_result(waiting_intent, outcome)
            log_execution_event(
                command=original_command,
                intent=waiting_intent,
                status=outcome.get("status", "follow_up_dispatched"),
                message=outcome.get("message"),
                action_outcome=outcome,
            )
            return True

    try:
        intent, confidence, _ = predict_intent(command)
    except Exception as exc:
        print(f"Intent prediction failed: {exc}")
        log_execution_event(
            command=command,
            intent=None,
            confidence=None,
            status="prediction_error",
            message=str(exc),
        )
        return True

    print(f"Intent: {intent}")
    print(f"Confidence: {confidence:.2%}")

    if explicit_stop and intent != "STOP_ASSISTANT":
        message = "I heard a stop request, but the classifier did not recognize it clearly. Please say 'stop listening'."
        print(message)
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="rejected_stop_mismatch",
            message=message,
        )
        return True

    if confidence < CONFIDENCE_THRESHOLD:
        message = "I'm not confident enough to execute that command."
        print(message)
        report_rejected_action(intent, message, "rejected_low_confidence")
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="rejected_low_confidence",
            message=message,
        )
        return True

    if intent == "STOP_ASSISTANT" and confidence < STOP_CONFIDENCE_THRESHOLD:
        message = "I need a clearer stop command."
        print(message)
        report_rejected_action(intent, message, "rejected_stop_low_confidence")
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="rejected_stop_low_confidence",
            message=message,
        )
        return True

    try:
        prepared = prepare_command(intent, command)
    except Exception as exc:
        print(f"Command routing failed: {exc}")
        report_rejected_action(intent, str(exc), "router_error")
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="router_error",
            message=str(exc),
        )
        return True

    status = prepared["status"]
    if status == "not_actionable":
        message = prepared.get("message") or "No computer action for this command."
        print(message)
        report_rejected_action(intent, message, status)
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="not_actionable",
            message=message,
        )
        return True

    if status == "needs_clarification":
        missing_args = prepared.get("arguments", {})
        message = prepared.get("message") or "Please provide more information."

        if (
            intent in {"SET_TIMER", "MAKE_NOTES", "SEARCH_WEB"}
            and missing_args.get("needs_clarification", False)
        ):
            session.set_pending(intent, command)

        print(message)
        report_rejected_action(
            intent,
            message,
            "pending_clarification" if session.has_pending() else status,
        )
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="pending_clarification" if session.has_pending() else "needs_clarification",
            message=message,
        )
        return True

    arguments = prepared.get("arguments", {})
    if arguments:
        print("Extracted arguments:", arguments)

    print("Executing...")
    try:
        loop_result = execute_intent(intent, command, arguments=arguments)
    except Exception as exc:
        print("Action error:", exc)
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="action_error",
            message=str(exc),
        )
        return True

    outcome = get_last_action_outcome() or {
        "intent": intent,
        "success": None,
        "status": "dispatched_unverified",
        "message": "Action result was unavailable.",
    }
    report_action_result(intent, outcome)

    if loop_result is False:
        log_execution_event(
            command=command,
            intent=intent,
            confidence=confidence,
            status="stop_requested",
            message=outcome.get("message"),
            action_outcome=outcome,
        )
        return False

    log_execution_event(
        command=command,
        intent=intent,
        confidence=confidence,
        status=outcome.get("status", "dispatched"),
        message=outcome.get("message"),
        action_outcome=outcome,
    )
    if outcome.get("success") is False:
        return True
    return True


# ============================================================
# 13. MAIN AGENT LOOP
# ============================================================

def main():

    print()
    print("=" * 60)
    print("        AI PC VOICE AGENT")
    print("=" * 60)

    print()
    print("Whisper model:", WHISPER_MODEL_NAME)
    print("Whisper device:", DEVICE)
    print("Recording duration:", DURATION, "seconds")
    print("Confidence threshold:", CONFIDENCE_THRESHOLD)
    print("Stop threshold:", STOP_CONFIDENCE_THRESHOLD)

    print()
    print("Agent ready.")
    print("Say 'stop listening' to stop the agent.")
    print("=" * 60)


    running = True

    while running:

        try:

            running = process_voice_command()

        except KeyboardInterrupt:

            print()
            print(
                "Assistant interrupted by keyboard."
            )

            break

        except Exception as e:

            print()
            print(
                "Unexpected error:",
                e
            )

            print(
                "Continuing..."
            )


    print()
    print("=" * 60)
    print("Assistant stopped.")
    print("=" * 60)


# ============================================================
# 14. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()