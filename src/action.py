"""
commands.py
Action layer for the Personal AI PC Voice Agent.

Designed for:
    Whisper -> Intent Classifier -> execute_intent(intent, command)

Windows commands are launched through PowerShell where useful, so this
can also be used when the Python agent is running inside WSL.

Main return convention:
    True  -> keep the agent running
    False -> stop the agent
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOME = Path.home()
DESKTOP = HOME / "Desktop"
DOCUMENTS = HOME / "Documents"
PICTURES = HOME / "Pictures"
DOWNLOADS = HOME / "Downloads"

# Override these with environment variables when required.
PROJECT_PATH = Path(
    os.environ.get("AI_AGENT_PROJECT_PATH", str(HOME / "Projects"))
)

NOTES_PATH = Path(
    os.environ.get(
        "AI_AGENT_NOTES_PATH",
        str(DOCUMENTS / "AI_Assistant_Notes.txt"),
    )
)

_last_action_outcome: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def powershell_available() -> bool:
    return shutil.which("powershell.exe") is not None or shutil.which("pwsh") is not None


def ps_exe() -> str:
    path = shutil.which("powershell.exe")
    if path:
        return path

    path = shutil.which("pwsh")
    if path:
        return path

    return "powershell.exe"


def run_powershell(command: str, wait: bool = True):
    """Run a PowerShell command."""
    args = [
        ps_exe(),
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        command,
    ]

    if wait:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )

    return subprocess.Popen(args)


def ps_quote(value: str) -> str:
    """Safely quote a string for a PowerShell single-quoted string."""
    return "'" + value.replace("'", "''") + "'"


def launch_windows_program(program: str, *args: str) -> bool:
    """Launch a Windows application/program."""
    try:
        command = (
            f"Start-Process -FilePath {ps_quote(program)}"
        )

        if args:
            quoted_args = " ".join(ps_quote(str(arg)) for arg in args)
            command += f" -ArgumentList {quoted_args}"

        result = run_powershell(command)

        if result.returncode != 0:
            print(result.stderr.strip() or f"Could not launch {program}.")
            return False

        return True

    except Exception as exc:
        print(f"Launch error: {exc}")
        return False


def open_url(url: str) -> bool:
    """Open URL in Microsoft Edge."""
    try:
        command = (
            f"Start-Process -FilePath 'msedge.exe' "
            f"-ArgumentList {ps_quote(url)}"
        )
        result = run_powershell(command)

        if result.returncode != 0:
            print(result.stderr.strip() or "Could not open Microsoft Edge.")
            return False

        return True

    except Exception as exc:
        print(f"Browser launch error: {exc}")
        return False


def normalize_command(command: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (command or "").strip())


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Application launching
# ---------------------------------------------------------------------------

def open_edge() -> bool:
    return launch_windows_program("msedge.exe")


def open_vscode() -> bool:
    vscode = shutil.which("code")

    if vscode:
        try:
            subprocess.Popen([vscode])
            return True
        except Exception as exc:
            print(f"VS Code launch error: {exc}")

    return launch_windows_program("code.exe")


def open_notepad() -> bool:
    return launch_windows_program("notepad.exe")


def open_file_explorer() -> bool:
    return launch_windows_program("explorer.exe")


def open_terminal() -> bool:
    # Windows Terminal
    return launch_windows_program("wt.exe")


def open_calculator() -> bool:
    return launch_windows_program("calc.exe")


def open_settings() -> bool:
    return launch_windows_program("ms-settings:")


def open_task_manager() -> bool:
    return launch_windows_program("taskmgr.exe")


def open_snipping_tool() -> bool:
    # Windows 11 / modern Windows
    if launch_windows_program("SnippingTool.exe"):
        return True

    return launch_windows_program("ms-screenclip:")


# ---------------------------------------------------------------------------
# Development actions
# ---------------------------------------------------------------------------

def open_project(command: Optional[str] = None) -> bool:
    """
    Opens the configured project directory.

    Set:
        AI_AGENT_PROJECT_PATH=C:\\Users\\YourName\\Projects\\MyProject

    or, from WSL, use the Windows-accessible path.
    """
    if not PROJECT_PATH.exists():
        print(f"Project path does not exist: {PROJECT_PATH}")
        print("Set AI_AGENT_PROJECT_PATH to your project directory.")
        return False

    return launch_windows_program(
        "explorer.exe",
        str(PROJECT_PATH),
    )


def start_jupyter() -> bool:
    try:
        # Prefer the current Python environment.
        if shutil.which("jupyter"):
            subprocess.Popen(["jupyter", "lab"])
            return True

        print("Jupyter was not found in the current Python environment.")
        return False

    except Exception as exc:
        print(f"Jupyter launch error: {exc}")
        return False


def open_python() -> bool:
    python_exe = shutil.which("python.exe") or shutil.which("python")

    if python_exe:
        try:
            subprocess.Popen([python_exe])
            return True
        except Exception as exc:
            print(f"Python launch error: {exc}")

    # WSL fallback: launch Windows Python if available.
    return launch_windows_program("python.exe")


def open_git_bash() -> bool:
    candidates = [
        r"C:\Program Files\Git\git-bash.exe",
        r"C:\Program Files\Git\bin\bash.exe",
    ]

    for candidate in candidates:
        if launch_windows_program(candidate):
            return True

    return False


def open_powershell() -> bool:
    return launch_windows_program("powershell.exe")


def open_command_prompt() -> bool:
    return launch_windows_program("cmd.exe")


def open_vscode_terminal() -> bool:
    """
    Opens VS Code, then sends Ctrl+Shift+` to toggle its integrated terminal.

    This uses a small PowerShell SendKeys call because the VS Code CLI does
    not provide a universal 'open integrated terminal' switch.
    """
    if not open_vscode():
        return False

    toggle_script = r"""
Start-Sleep -Milliseconds 1200
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("^+`")
"""

    run_powershell(toggle_script, wait=False)
    return True


def extract_script_path(command: Optional[str]) -> Optional[str]:
    text = normalize_command(command)

    patterns = [
        r"\brun (?:the )?(?:python )?script (?:at |called |named )(.+)$",
        r"\bexecute (?:the )?(?:python )?script (?:at |called |named )(.+)$",
        r"\brun (?:the )?python file (?:at |called |named )(.+)$",
        r"\bexecute (?:the )?python file (?:at |called |named )(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .")

    # When the classifier says RUN_PYTHON_SCRIPT but the user did not
    # specify a path, let the caller decide what the current script is.
    return None


def run_python_script(command: Optional[str] = None) -> bool:
    script = extract_script_path(command)

    if script:
        script = os.path.expandvars(os.path.expanduser(script.strip('"')))

        if not os.path.isabs(script):
            script = str(Path.cwd() / script)

        if not Path(script).exists():
            print(f"Python script not found: {script}")
            return False
    else:
        print("No script path was provided.")
        print("Set command examples such as: run the Python script C:\\path\\app.py")
        return False

    python_exe = shutil.which("python.exe") or shutil.which("python")

    if not python_exe:
        print("Python executable was not found.")
        return False

    try:
        subprocess.Popen([python_exe, script])
        print(f"Running Python script: {script}")
        return True
    except Exception as exc:
        print(f"Could not run Python script: {exc}")
        return False


# ---------------------------------------------------------------------------
# Web actions
# ---------------------------------------------------------------------------

def extract_search_query(command: Optional[str]) -> Optional[str]:
    text = normalize_command(command)

    patterns = [
        r"^search the web for (.+)$",
        r"^search the internet for (.+)$",
        r"^search for (.+)$",
        r"^look up (.+)$",
        r"^look for (.+)$",
        r"^find (.+) online$",
        r"^find information about (.+)$",
        r"^find (.+)$",
        r"^search (.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            query = match.group(1).strip(" .?!")
            if query and query.lower() != "search":
                return query

    return None


def search_web(
    command: Optional[str] = None,
    *,
    query: Optional[str] = None
) -> bool:
    # Use the already-extracted query when supplied.
    if query is None:
        query = extract_search_query(command)

    query = normalize_command(query)

    if not query:
        print("What would you like me to search for?")
        return True

    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded_query}"

    print(f"Searching for: {query}")
    return open_url(url)

KNOWN_WEBSITES = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "google": "https://www.google.com",
    "linkedin": "https://www.linkedin.com",
    "wikipedia": "https://www.wikipedia.org",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "reddit": "https://www.reddit.com",
    "x": "https://x.com",
    "twitter": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
}


def extract_website_target(command: Optional[str]) -> Optional[str]:
    text = normalize_command(command)

    patterns = [
        r"^(?:open|visit|go to|take me to)\s+(.+)$",
        r"^(?:launch)\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            target = match.group(1).strip(" .?!")
            if target:
                return target

    return None


def website_to_url(target: str) -> str:
    cleaned = target.strip().lower()

    if cleaned in KNOWN_WEBSITES:
        return KNOWN_WEBSITES[cleaned]

    # Remove conversational suffixes.
    cleaned = re.sub(r"\b(website|site|homepage)$", "", cleaned).strip()

    if cleaned in KNOWN_WEBSITES:
        return KNOWN_WEBSITES[cleaned]

    if cleaned.startswith(("http://", "https://")):
        return cleaned

    # If it looks like a domain, use it directly.
    if "." in cleaned and " " not in cleaned:
        return "https://" + cleaned

    # General target: search it, rather than guessing a domain.
    return "https://www.bing.com/search?q=" + urllib.parse.quote_plus(target)


def open_website(command: Optional[str]) -> bool:
    target = extract_website_target(command)

    if not target:
        print("Which website should I open?")
        return True

    url = website_to_url(target)
    print(f"Opening: {target}")
    return open_url(url)


def open_youtube() -> bool:
    return open_url("https://www.youtube.com")


def open_github() -> bool:
    return open_url("https://github.com")


def open_gmail() -> bool:
    return open_url("https://mail.google.com")


def open_google_drive() -> bool:
    return open_url("https://drive.google.com")


def open_chatgpt() -> bool:
    return open_url("https://chatgpt.com")


# ---------------------------------------------------------------------------
# System information
# ---------------------------------------------------------------------------

def check_cpu() -> bool:
    try:
        result = subprocess.run(
            ["lscpu"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            print(result.stdout)
            return True

    except FileNotFoundError:
        pass

    result = run_powershell(
        "Get-CimInstance Win32_Processor | "
        "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,"
        "MaxClockSpeed | Format-List"
    )

    print(result.stdout)
    return result.returncode == 0


def check_gpu() -> bool:
    nvidia = shutil.which("nvidia-smi")

    if nvidia:
        try:
            result = subprocess.run(
                [nvidia, "--query-gpu=name,driver_version,memory.total",
                 "--format=csv"],
                capture_output=True,
                text=True,
                check=False,
            )
            print(result.stdout)
            return result.returncode == 0
        except Exception as exc:
            print(f"GPU query error: {exc}")

    result = run_powershell(
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,DriverVersion,AdapterRAM | Format-List"
    )

    print(result.stdout)
    return result.returncode == 0


def check_ram() -> bool:
    result = run_powershell(
        "$os = Get-CimInstance Win32_OperatingSystem; "
        "$total = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2); "
        "$free = [math]::Round($os.FreePhysicalMemory / 1MB, 2); "
        "$used = [math]::Round($total - $free, 2); "
        "[pscustomobject]@{TotalGB=$total;UsedGB=$used;FreeGB=$free} | "
        "Format-List"
    )

    print(result.stdout)
    return result.returncode == 0


def check_disk() -> bool:
    result = run_powershell(
        "Get-PSDrive -PSProvider FileSystem | "
        "Where-Object {$_.Used -ne $null} | "
        "Select-Object Name,"
        "@{N='UsedGB';E={[math]::Round($_.Used/1GB,2)}},"
        "@{N='FreeGB';E={[math]::Round($_.Free/1GB,2)}} | "
        "Format-Table -AutoSize"
    )

    print(result.stdout)
    return result.returncode == 0


def check_windows_version() -> bool:
    result = run_powershell(
        "Get-ComputerInfo | "
        "Select-Object WindowsProductName,WindowsVersion,OsBuildNumber | "
        "Format-List"
    )

    print(result.stdout)
    return result.returncode == 0


def check_ip_address() -> bool:
    result = run_powershell(
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object {$_.IPAddress -notlike '127.*'} | "
        "Select-Object InterfaceAlias,IPAddress | "
        "Format-Table -AutoSize"
    )

    print(result.stdout)
    return result.returncode == 0


def check_battery() -> bool:
    result = run_powershell(
        "Get-CimInstance Win32_Battery | "
        "Select-Object EstimatedChargeRemaining,BatteryStatus | "
        "Format-List"
    )

    print(result.stdout)

    if result.returncode != 0:
        return False

    if not result.stdout.strip():
        print("No battery information was reported. This may be a desktop PC.")

    return True


def check_network() -> bool:
    result = run_powershell(
        "Get-NetConnectionProfile | "
        "Select-Object Name,InterfaceAlias,NetworkCategory,IPv4Connectivity,"
        "IPv6Connectivity | Format-Table -AutoSize"
    )

    print(result.stdout)
    return result.returncode == 0


def check_process_list() -> bool:
    result = run_powershell(
        "Get-Process | "
        "Sort-Object CPU -Descending | "
        "Select-Object -First 25 Name,Id,"
        "@{N='CPU_s';E={[math]::Round($_.CPU,2)}} | "
        "Format-Table -AutoSize"
    )

    print(result.stdout)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# System control
# ---------------------------------------------------------------------------

def lock_computer() -> bool:
    try:
        subprocess.Popen(
            ["rundll32.exe", "user32.dll,LockWorkStation"]
        )
        return True
    except Exception as exc:
        print(f"Could not lock computer: {exc}")
        return False


def sleep_computer() -> bool:
    result = run_powershell(
        "Add-Type -AssemblyName System.Windows.Forms; "
        "[System.Windows.Forms.Application]::SetSuspendState("
        "'Suspend', $false, $false)"
    )
    return result.returncode == 0


def _media_key(vk_code: int) -> bool:
    """
    Send a Windows media/sound virtual key.
    VK codes:
        0xAD = Volume mute
        0xAE = Volume down
        0xAF = Volume up
        0xB0 = Next track
        0xB1 = Previous track
        0xB3 = Play/Pause
    """
    script = f"""
Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class NativeKeys {{
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
}}
'@

[NativeKeys]::keybd_event({vk_code}, 0, 0, [UIntPtr]::Zero)
[NativeKeys]::keybd_event({vk_code}, 0, 2, [UIntPtr]::Zero)
"""

    result = run_powershell(script)
    return result.returncode == 0


def mute_audio() -> bool:
    return _media_key(0xAD)


def unmute_audio() -> bool:
    return _media_key(0xAD)


def increase_volume() -> bool:
    return _media_key(0xAF)


def decrease_volume() -> bool:
    return _media_key(0xAE)


def screenshot() -> bool:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DESKTOP / f"Screenshot_{timestamp}.png"

    script = f"""
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)

$graphics.CopyFromScreen(
    $bounds.X,
    $bounds.Y,
    0,
    0,
    $bitmap.Size
)

$bitmap.Save({ps_quote(str(path))},
    [System.Drawing.Imaging.ImageFormat]::Png)

$graphics.Dispose()
$bitmap.Dispose()
"""

    result = run_powershell(script)
    if result.returncode != 0:
        print(result.stderr.strip())
        return False

    print(f"Screenshot saved to: {path}")
    return True


def open_notification_settings() -> bool:
    return launch_windows_program(
        "ms-settings:notifications"
    )


def toggle_wifi(command: Optional[str] = None) -> bool:
    text = normalize_command(command).lower()

    if any(word in text for word in ["off", "disable", "disconnect"]):
        state = "disabled"
    elif any(word in text for word in ["on", "enable", "connect"]):
        state = "enabled"
    else:
        print("Say whether you want Wi-Fi on or off.")
        return True

    script = f"""
$adapter = Get-NetAdapter |
    Where-Object {{
        $_.Name -match 'Wi-?Fi|WLAN' -or
        $_.InterfaceDescription -match 'Wireless|Wi-?Fi|WLAN'
    }} |
    Select-Object -First 1

if ($null -eq $adapter) {{
    Write-Error "Wi-Fi adapter was not found."
    exit 1
}}

Disable-NetAdapter -Name $adapter.Name -Confirm:$false
""" if state == "disabled" else f"""
$adapter = Get-NetAdapter |
    Where-Object {{
        $_.Name -match 'Wi-?Fi|WLAN' -or
        $_.InterfaceDescription -match 'Wireless|Wi-?Fi|WLAN'
    }} |
    Select-Object -First 1

if ($null -eq $adapter) {{
    Write-Error "Wi-Fi adapter was not found."
    exit 1
}}

Enable-NetAdapter -Name $adapter.Name -Confirm:$false
"""

    result = run_powershell(script)

    if result.returncode != 0:
        print(result.stderr.strip())
        print("Wi-Fi control may require administrator privileges.")
        return False

    print(f"Wi-Fi {state}.")
    return True


# ---------------------------------------------------------------------------
# Files and folders
# ---------------------------------------------------------------------------

def open_downloads() -> bool:
    return launch_windows_program("explorer.exe", str(DOWNLOADS))


def open_documents() -> bool:
    return launch_windows_program("explorer.exe", str(DOCUMENTS))


def open_desktop() -> bool:
    return launch_windows_program("explorer.exe", str(DESKTOP))


def open_pictures() -> bool:
    return launch_windows_program("explorer.exe", str(PICTURES))


def open_project_folder() -> bool:
    return open_project()


def extract_named_item(
    command: Optional[str],
    item_type: str,
) -> Optional[str]:
    text = normalize_command(command)

    if item_type == "folder":
        patterns = [
            r"\bcreate a folder named (.+)$",
            r"\bcreate a folder called (.+)$",
            r"\bmake a new folder called (.+)$",
            r"\bmake a new folder named (.+)$",
            r"\bmake a directory called (.+)$",
            r"\bcreate a directory named (.+)$",
        ]
    else:
        patterns = [
            r"\bcreate a text file named (.+)$",
            r"\bcreate a text file called (.+)$",
            r"\bmake a new text file called (.+)$",
            r"\bmake a new text file named (.+)$",
            r"\bcreate a file named (.+)$",
            r"\bcreate a file called (.+)$",
            r"\bmake a text document called (.+)$",
        ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .?!\"'")
            return value or None

    return None


def sanitize_filename(name: str) -> str:
    # Windows-invalid filename characters
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip().rstrip(".")
    return name


def create_folder(command: Optional[str]) -> bool:
    name = extract_named_item(command, "folder")

    if not name:
        print("Please specify the folder name.")
        return True

    name = sanitize_filename(name)
    target = DESKTOP / name

    try:
        target.mkdir(parents=True, exist_ok=False)
        print(f"Folder created: {target}")
        return True
    except FileExistsError:
        print(f"Folder already exists: {target}")
        return True
    except Exception as exc:
        print(f"Could not create folder: {exc}")
        return False


def create_text_file(command: Optional[str]) -> bool:
    name = extract_named_item(command, "file")

    if not name:
        print("Please specify the text file name.")
        return True

    name = sanitize_filename(name)

    if not name.lower().endswith(".txt"):
        name += ".txt"

    target = DESKTOP / name

    try:
        target.write_text("", encoding="utf-8")
        print(f"Text file created: {target}")
        return True
    except FileExistsError:
        print(f"File already exists: {target}")
        return True
    except Exception as exc:
        print(f"Could not create text file: {exc}")
        return False


# ---------------------------------------------------------------------------
# Productivity
# ---------------------------------------------------------------------------

def extract_note(command: Optional[str]) -> Optional[str]:
    text = normalize_command(command)

    patterns = [
        r"make a note saying (.+)$",
        r"make a note that (.+)$",
        r"take a note saying (.+)$",
        r"take a note that (.+)$",
        r"write this down[: ]+(.+)$",
        r"make notes about (.+)$",
        r"take notes about (.+)$",
        r"create a note saying (.+)$",
        r"create a note that (.+)$",
        r"write down (.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .?!\"'")

    return None


def make_notes(
    command: Optional[str] = None,
    *,
    content: Optional[str] = None
) -> bool:
    # Use the extracted note content when supplied.
    if content is None:
        note = extract_note(command)
    else:
        note = normalize_command(content)

    if not note:
        print("What would you like me to write in the note?")
        return True

    try:
        ensure_parent(NOTES_PATH)

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        with NOTES_PATH.open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {note}\n")

        print(f"Note saved: {note}")
        print(f"Notes file: {NOTES_PATH}")

        open_notes()
        return True

    except Exception as exc:
        print(f"Could not save note: {exc}")
        return False

def open_notes() -> bool:
    try:
        ensure_parent(NOTES_PATH)
        NOTES_PATH.touch(exist_ok=True)
        return launch_windows_program("notepad.exe", str(NOTES_PATH))
    except Exception as exc:
        print(f"Could not open notes: {exc}")
        return False


def extract_duration_seconds(command: Optional[str]) -> Optional[int]:
    text = normalize_command(command).lower()

    number_words = {
        "a": 1,
        "an": 1,
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
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
    }

    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
        text,
    )

    if match:
        value = float(match.group(1))
        unit = match.group(2)

        if unit.startswith("hour") or unit.startswith("hr"):
            return int(value * 3600)
        if unit.startswith("minute") or unit.startswith("min"):
            return int(value * 60)
        return int(value)

    # Basic spoken-number support, including "forty five minutes".
    match = re.search(
        r"\b([a-z]+)(?:\s+([a-z]+))?\s*(seconds?|minutes?|hours?|mins?|hrs?)\b",
        text,
    )

    if match:
        first = number_words.get(match.group(1))
        second = number_words.get(match.group(2)) if match.group(2) else 0

        if first is not None:
            value = first + (second or 0)
            unit = match.group(3)

            if unit.startswith("hour") or unit.startswith("hr"):
                return value * 3600
            if unit.startswith("minute") or unit.startswith("min"):
                return value * 60
            return value

    return None


def set_timer(
    command: Optional[str] = None,
    *,
    duration_seconds: Optional[int] = None
) -> bool:
    # Prefer the extracted argument; otherwise use the existing parser.
    if duration_seconds is None:
        seconds = extract_duration_seconds(command)
    else:
        seconds = duration_seconds

    if seconds is None or seconds <= 0:
        print("Please provide a valid timer duration.")
        return True

    minutes, remainder = divmod(seconds, 60)
    print(f"Timer started for {minutes}m {remainder}s.")

    # Keep the existing asynchronous Windows timer behavior.
    script = f"""
Start-Sleep -Seconds {seconds}
[console]::beep(1000, 700)
Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show(
    'Your timer is finished.',
    'AI PC Voice Agent'
)
"""

    run_powershell(script, wait=False)
    return True

def extract_reminder_text(command: Optional[str]) -> Optional[str]:
    text = normalize_command(command)

    patterns = [
        r"set a reminder to (.+)$",
        r"set a reminder for (.+)$",
        r"remind me to (.+)$",
        r"remind me about (.+)$",
        r"create a reminder to (.+)$",
        r"create a reminder for (.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .?!")

    return None


def set_reminder(command: Optional[str]) -> bool:
    reminder = extract_reminder_text(command)

    if not reminder:
        print("What should I remind you about?")
        return True

    # Store the request in a simple local reminder log. A later scheduler
    # integration can consume this file.
    reminder_file = DOCUMENTS / "AI_Assistant_Reminders.txt"
    ensure_parent(reminder_file)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with reminder_file.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {reminder}\n")

    print(f"Reminder saved: {reminder}")
    print(
        f"Reminder log: {reminder_file}\n"
        "Note: exact calendar/notification scheduling should be handled "
        "by a dedicated scheduler layer."
    )

    return True


def check_time() -> bool:
    print(datetime.now().strftime("Current time: %I:%M:%S %p"))
    return True


# ---------------------------------------------------------------------------
# Media controls
# ---------------------------------------------------------------------------

def play_media() -> bool:
    return _media_key(0xB3)


def pause_media() -> bool:
    # Windows exposes Play/Pause as a toggle.
    return _media_key(0xB3)


def next_track() -> bool:
    return _media_key(0xB0)


# ---------------------------------------------------------------------------
# Agent control
# ---------------------------------------------------------------------------

ASSISTANT_PAUSED = False


def stop_assistant() -> bool:
    print("Stopping the AI PC Voice Agent.")
    return False


def pause_listening() -> bool:
    global ASSISTANT_PAUSED
    ASSISTANT_PAUSED = True
    print("Voice listening paused.")
    return True


def resume_listening() -> bool:
    global ASSISTANT_PAUSED
    ASSISTANT_PAUSED = False
    print("Voice listening resumed.")
    return True


def show_agent_status() -> bool:
    state = "PAUSED" if ASSISTANT_PAUSED else "LISTENING"
    print(f"AI PC Voice Agent: {state}")
    return True


# ---------------------------------------------------------------------------
# Intent dispatcher
# ---------------------------------------------------------------------------

ACTIONS = {
    # Application launching
    "OPEN_EDGE": open_edge,
    "OPEN_VSCODE": open_vscode,
    "OPEN_NOTEPAD": open_notepad,
    "OPEN_FILE_EXPLORER": open_file_explorer,
    "OPEN_TERMINAL": open_terminal,
    "OPEN_CALCULATOR": open_calculator,
    "OPEN_SETTINGS": open_settings,
    "OPEN_TASK_MANAGER": open_task_manager,
    "OPEN_SNIPPING_TOOL": open_snipping_tool,

    # Development
    "OPEN_PROJECT": open_project,
    "START_JUPYTER": start_jupyter,
    "OPEN_PYTHON": open_python,
    "OPEN_GIT_BASH": open_git_bash,
    "OPEN_POWERSHELL": open_powershell,
    "OPEN_COMMAND_PROMPT": open_command_prompt,
    "OPEN_VSCODE_TERMINAL": open_vscode_terminal,
    "RUN_PYTHON_SCRIPT": run_python_script,

    # Web
    "SEARCH_WEB": search_web,
    "OPEN_WEBSITE": open_website,
    "OPEN_YOUTUBE": open_youtube,
    "OPEN_GITHUB": open_github,
    "OPEN_GMAIL": open_gmail,
    "OPEN_GOOGLE_DRIVE": open_google_drive,
    "OPEN_CHATGPT": open_chatgpt,

    # System information
    "CHECK_CPU": check_cpu,
    "CHECK_GPU": check_gpu,
    "CHECK_RAM": check_ram,
    "CHECK_DISK": check_disk,
    "CHECK_WINDOWS_VERSION": check_windows_version,
    "CHECK_IP_ADDRESS": check_ip_address,
    "CHECK_BATTERY": check_battery,
    "CHECK_NETWORK": check_network,
    "CHECK_PROCESS_LIST": check_process_list,

    # System control
    "LOCK_COMPUTER": lock_computer,
    "SLEEP_COMPUTER": sleep_computer,
    "MUTE_AUDIO": mute_audio,
    "UNMUTE_AUDIO": unmute_audio,
    "INCREASE_VOLUME": increase_volume,
    "DECREASE_VOLUME": decrease_volume,
    "SCREENSHOT": screenshot,
    "OPEN_NOTIFICATION_SETTINGS": open_notification_settings,
    "TOGGLE_WIFI": toggle_wifi,

    # Files/folders
    "OPEN_DOWNLOADS": open_downloads,
    "OPEN_DOCUMENTS": open_documents,
    "OPEN_DESKTOP": open_desktop,
    "OPEN_PICTURES": open_pictures,
    "CREATE_FOLDER": create_folder,
    "CREATE_TEXT_FILE": create_text_file,

    # Productivity
    "MAKE_NOTES": make_notes,
    "OPEN_NOTES": open_notes,
    "SET_TIMER": set_timer,
    "SET_REMINDER": set_reminder,
    "CHECK_TIME": check_time,

    # Media
    "PLAY_MEDIA": play_media,
    "PAUSE_MEDIA": pause_media,
    "NEXT_TRACK": next_track,

    # Agent
    "STOP_ASSISTANT": stop_assistant,
    "PAUSE_LISTENING": pause_listening,
    "RESUME_LISTENING": resume_listening,
    "SHOW_AGENT_STATUS": show_agent_status,
}


ENTITY_INTENTS = {
    "SEARCH_WEB",
    "OPEN_WEBSITE",
    "OPEN_PROJECT",
    "RUN_PYTHON_SCRIPT",
    "TOGGLE_WIFI",
    "CREATE_FOLDER",
    "CREATE_TEXT_FILE",
    "MAKE_NOTES",
    "SET_TIMER",
    "SET_REMINDER",
}



def execute_intent(
    intent: str,
    command: Optional[str] = None,
    arguments: Optional[dict] = None,
) -> bool:
    """Execute an action; return False only to stop the agent."""
    global _last_action_outcome
    _last_action_outcome = None

    if not intent:
        print("No intent received.")
        _last_action_outcome = {
            "intent": None,
            "success": False,
            "status": "rejected",
            "message": "No intent received.",
        }
        return True

    intent = intent.strip().upper()

    if intent == "UNKNOWN":
        print("No computer action for this command.")
        _last_action_outcome = {
            "intent": intent,
            "success": False,
            "status": "unsupported",
            "message": "No computer action for this command.",
        }
        return True

    action = ACTIONS.get(intent)

    if action is None:
        print("Unknown intent:", intent)
        _last_action_outcome = {
            "intent": intent,
            "success": False,
            "status": "unsupported",
            "message": f"Unknown intent: {intent}.",
        }
        return True

    try:
        # The agent should stop only for this explicit intent.
        if intent == "STOP_ASSISTANT":
            action()
            _last_action_outcome = {
                "intent": intent,
                "success": True,
                "status": "stop_requested",
                "message": "Assistant stop requested.",
            }
            return False

        argument_intents = {
            "SEARCH_WEB",
            "MAKE_NOTES",
            "SET_TIMER",
        }

        if intent in argument_intents:
            if arguments is None:
                from command_router import prepare_command

                prepared = prepare_command(intent, command or "")

                if prepared["status"] != "ready":
                    message = (
                        prepared.get("message")
                        or "This command needs more information."
                    )
                    print(message)
                    _last_action_outcome = {
                        "intent": intent,
                        "success": False,
                        "status": "rejected",
                        "message": message,
                    }
                    return True

                arguments = prepared["arguments"]

            if intent == "SEARCH_WEB":
                result = search_web(
                    query=arguments.get("query")
                )

            elif intent == "MAKE_NOTES":
                result = make_notes(
                    content=arguments.get("content")
                )

            else:
                seconds = arguments.get("duration_seconds")

                if seconds is None:
                    seconds = extract_duration_seconds(command)

                if seconds is None or seconds <= 0:
                    message = "How long should I set the timer for?"
                    print(message)
                    _last_action_outcome = {
                        "intent": intent,
                        "success": False,
                        "status": "rejected",
                        "message": message,
                    }
                    return True

                result = set_timer(
                    duration_seconds=seconds
                )

        elif intent in ENTITY_INTENTS:
            result = action(command)

        else:
            result = action()

        if result is False:
            message = (
                f"Action '{intent}' reported failure. "
                "The assistant will continue listening."
            )
            print(
                message
            )
            _last_action_outcome = {
                "intent": intent,
                "success": False,
                "status": "failed",
                "message": message,
            }
        elif result is True:
            _last_action_outcome = {
                "intent": intent,
                "success": True,
                "status": "completed",
                "message": f"{intent} completed successfully.",
            }
        else:
            _last_action_outcome = {
                "intent": intent,
                "success": None,
                "status": "dispatched_unverified",
                "message": (
                    f"{intent} was dispatched, but its completion "
                    "could not be verified."
                ),
            }

        return True

    except Exception as exc:
        print(f"Action '{intent}' failed: {exc}")
        print("The assistant will continue listening.")
        _last_action_outcome = {
            "intent": intent,
            "success": False,
            "status": "exception",
            "message": str(exc),
        }
        return True


def get_last_action_outcome() -> Optional[dict[str, Any]]:
    """Return a copy of the most recent action outcome, if any."""
    return _last_action_outcome.copy() if _last_action_outcome else None


# ---------------------------------------------------------------------------
# Optional command-line test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("OPEN_EDGE", "open Microsoft Edge"),
        ("OPEN_VSCODE", "launch VS Code"),
        ("SEARCH_WEB", "search for TensorFlow GPU setup"),
        ("MAKE_NOTES", "make a note saying finish my ML project"),
        ("CHECK_TIME", "what time is it"),
    ]

    for intent, command in tests:
        print("\n" + "=" * 60)
        print(f"Intent : {intent}")
        print(f"Command: {command}")
        (intent, command)
