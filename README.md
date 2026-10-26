# AI PC Voice Assistant

An AI-powered desktop voice assistant that listens to spoken commands,
transcribes speech with Whisper, predicts the user's intent with a
TensorFlow/Keras classifier, plans compound commands, extracts command
arguments, and dispatches actions through a modular execution pipeline.

> **Project status:** Core command pipeline and integration tests are in
> place. The existing model is used as-is; model retraining/accuracy
> tuning is not part of the current usage workflow. Text-to-speech (TTS)
> is a planned next step, not a completed feature.

## Current capabilities

-   **Speech-to-text:** OpenAI Whisper transcription (configured in the
    current application; the project has used `base.en`).
-   **Intent classification:** TensorFlow/Keras LSTM model with 61
    intent classes.
-   **Command planning:** Splits supported compound requests into
    ordered steps where appropriate.
-   **Command routing and validation:** Checks whether a transcript is
    actionable and rejects certain unclear, repetitive, or mismatched
    requests.
-   **Entity extraction:** Extracts values such as web-search queries
    and timer durations.
-   **Action dispatch:** Routes recognized intents to existing
    desktop/system actions.
-   **Follow-up handling:** Supports clarification/pending-input flows
    for commands such as timers, notes, and web searches.
-   **Execution outcomes and responses:** Reports completed, failed, or
    unconfirmed actions without treating every ordinary action failure
    as a reason to stop the assistant.
-   **Execution logging:** Stores structured execution events in JSONL,
    with note content intended to be redacted.
-   **Session controls:** Handles the existing assistant session flow,
    including the stop-assistant intent.

The real-world availability of individual actions depends on the host
OS, installed applications, permissions, and the action implementations
in this checkout.

## Project layout

The main code is under `src/`:

``` text
Voice_assistant/
├── src/
│   ├── voice-agent.py
│   ├── action.py
│   ├── planner.py
│   ├── command_router.py
│   ├── entity_extractor.py
│   ├── response.py
│   ├── execution_logger.py
│   └── session_controller.py
├── data/
│   ├── intent_model_lstm_v4.keras
│   └── intent_metadata_lstm.json
├── tests/
│   └── test_action_results.py
└── logs/
    └── execution_history.jsonl   # created when events are logged
```

The model/metadata filenames above reflect the current project
configuration described for this version. If your checkout stores them
elsewhere, use the paths configured in `src/voice-agent.py` as the
source of truth.

## Requirements

-   Ubuntu/WSL environment or another environment supported by the code.
-   Python version compatible with the project's installed TensorFlow
    and audio packages.
-   Project dependencies installed in the project's virtual environment.
-   Microphone access and the required audio libraries for live speech
    input.
-   Model and metadata files available at the paths configured in
    `src/voice-agent.py`.
-   Internet access may be needed for initial Whisper model download and
    for web-search actions.
-   Windows integration actions may require WSL interop, Windows
    PowerShell, and the relevant Windows applications to be installed.

GPU acceleration is optional only if the current dependency/model setup
supports CPU execution; startup speed and inference performance may
differ.

## Setup

Run these commands from the project root:

``` bash
cd ~/projects/Voice_assistant
```

Activate the existing virtual environment:

``` bash
source tf_env/bin/activate
```

If the virtual environment or dependencies have not been set up yet,
inspect the repository for its dependency file first:

``` bash
ls
```

If `requirements.txt` exists, install its pinned dependencies:

``` bash
python -m pip install -r requirements.txt
```

Do not install a new TensorFlow, PyTorch, CUDA, or audio stack blindly
over a working environment. Use the dependency versions already
established by the project where possible.

## Verify the model files

Before launching, confirm that the model and metadata files exist in the
locations configured in `src/voice-agent.py`. The current expected
filenames are:

``` text
data/intent_model_lstm_v4.keras
data/intent_metadata_lstm.json
```

The metadata is required alongside the model because it provides
information used by inference, such as the intent mapping, vocabulary,
and maximum sequence length. Do not rename, regenerate, or retrain these
files as part of ordinary use.

From the project root, you can check the expected paths with:

``` bash
ls -lh data/intent_model_lstm_v4.keras data/intent_metadata_lstm.json
```

If that command reports missing files, inspect the actual model and
metadata paths referenced in `src/voice-agent.py` and use those paths;
do not create placeholder files.

## Run the assistant

From the project root, with the virtual environment activated:

``` bash
python src/voice-agent.py
```

Wait for the application to finish loading its model and audio
components. Follow the prompts printed by the program, then speak a
short, clear command. Use the stop-assistant command supported by the
current intent configuration to exit.

To stop a process that is stuck during development, use `Ctrl+C` in the
terminal.

## Example commands to try

Speak naturally and pause briefly after the command. These are examples
of the command types supported by the current pipeline; exact wording
and available actions depend on the trained intent labels and installed
action implementations.

  Goal                         Example phrase
  ---------------------------- ---------------------------------------
  Open an application          "Open Edge"
  Search the web               "Search for TensorFlow GPU setup"
  Run a compound command       "Open Edge and search for GPT"
  Request system information   "Check CPU"
  Request GPU information      "Check GPU"
  Set a timer                  "Set a timer for five minutes"
  Create a note                "Make a note to finish my ML project"

For a compound request, the planner may split the request into ordered
steps. If the assistant asks for clarification, answer with the missing
information rather than repeating the entire command. If a command is
rejected as unclear or low-confidence, rephrase it once using a short,
explicit instruction.

## Tests and validation

The latest reported integration run passed **22 tests** covering action
outcomes, planner behavior, routing/entity extraction, multi-step
execution, session handling, and logging. These tests mock external side
effects; they do not prove that microphone input, actual Windows
application launches, or every system action works on every machine.

Run the tests from the project root:

``` bash
python -m unittest discover -s tests -p 'test*.py' -v
```

Run syntax checks:

``` bash
python -m py_compile \
  src/action.py \
  src/planner.py \
  src/command_router.py \
  src/entity_extractor.py \
  src/response.py \
  src/execution_logger.py \
  src/session_controller.py \
  src/voice-agent.py \
  tests/test_action_results.py
```

## Logs

Execution events are written to a JSON Lines (`.jsonl`) log. The
configured path is expected to be under the project's `logs/` directory,
for example:

``` text
logs/execution_history.jsonl
```

Each line represents an individual event. Check the `LOG_FILE` setting
in `src/execution_logger.py` for the exact location. Do not share logs
publicly without reviewing them for commands or other private
information, even when note content is redacted.

## Troubleshooting

### Model or metadata file not found

Check the configured paths in `src/voice-agent.py`. Keep the model and
its matching metadata together as expected by the code.

### Microphone or transcription fails

Check that the microphone is available to the environment, required
audio dependencies are installed, and the OS grants microphone access.
Try a short command in a quiet environment.

### TensorFlow/CUDA warning or slow startup

Some TensorFlow messages concern GPU initialization or kernel
compilation and may not indicate a fatal error. Confirm that the
application continues loading and can run inference before treating a
warning as a failure. The first run may also download Whisper model
files.

### Windows application does not open from WSL

Confirm WSL interop is available, the relevant Windows executable is
installed, and the action implementation uses a valid executable path.
An action mocked in a unit test is not proof that the real application
can launch.

### A command is misunderstood

Use a short, direct phrase. The intent model has 61 classes, so not
every possible sentence is guaranteed to map to the intended action.
This is a model limitation; routine use does not require retraining the
model.

### Timer, notes, or search asks a follow-up

Provide the requested missing value. Pending-command behavior depends on
the current session implementation and should not be bypassed by
entering unrelated commands before answering.

## Current limitations and next milestone

-   TTS/spoken responses are planned but should not be considered
    complete until integrated and tested.
-   Live microphone, Whisper inference, actual desktop actions, timer
    notifications, and note-file creation require manual testing on the
    target machine.
-   Action availability can vary between Linux, WSL, and native Windows.
-   The 22-test suite validates the mocked integration contracts, not
    every end-to-end environment behavior.
-   The current model is retained as-is. Improving its accuracy is
    deliberately outside the current implementation milestone.

## Development principle

Preserve the existing model and working command pipeline. Make focused
changes, run the existing test suite after meaningful integration work,
and validate hardware/OS-dependent behavior manually rather than
assuming mocked tests prove it works.
