"""Platform detection and cross-OS utilities for EvoCoder."""

import platform
import os

# ---------------------------------------------------------------------------
# Platform flags
# ---------------------------------------------------------------------------
SYSTEM = platform.system().lower()

IS_WINDOWS = SYSTEM == "windows"
IS_MACOS = SYSTEM == "darwin"
IS_LINUX = SYSTEM == "linux"


# ---------------------------------------------------------------------------
# Platform info
# ---------------------------------------------------------------------------
def get_platform_info() -> dict:
    """Return a dict of platform details useful for logging and diagnostics."""
    return {
        "system": SYSTEM,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "is_linux": IS_LINUX,
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "shell": "cmd.exe" if IS_WINDOWS else os.environ.get("SHELL", "/bin/sh"),
    }


# ---------------------------------------------------------------------------
# Platform prompt
# ---------------------------------------------------------------------------
def get_platform_prompt() -> str:
    """Return platform-specific shell rules suitable for LLM system prompts."""
    if IS_WINDOWS:
        return (
            "PLATFORM: Windows\n"
            "- Use cmd.exe syntax by default (PowerShell is also available).\n"
            "- Use backslash (\\) path separators in cmd.exe; forward slash works in PowerShell.\n"
            "- Chain commands with & not && (cmd.exe), or ; in PowerShell.\n"
            "- Use dir instead of ls, del instead of rm, move instead of mv, copy instead of cp.\n"
            "- Environment variables: %VAR% in cmd.exe, $env:VAR in PowerShell.\n"
            "- Use NUL instead of /dev/null.\n"
            "- Python scripts run with `python` (not python3).\n"
            "- File paths may contain spaces; wrap in double quotes.\n"
        )
    if IS_MACOS:
        return (
            "PLATFORM: macOS\n"
            "- Use /bin/bash or /bin/zsh syntax.\n"
            "- Forward slash (/) path separators.\n"
            "- Commands: ls, rm, mv, cp, etc.\n"
            "- Use python3 (macOS ships Python 3 as python3).\n"
            "- brew is available for package management.\n"
        )
    # Linux
    return (
        "PLATFORM: Linux\n"
        "- Use /bin/bash or /bin/sh syntax.\n"
        "- Forward slash (/) path separators.\n"
        "- Commands: ls, rm, mv, cp, etc.\n"
        "- Use python3.\n"
        "- Package managers vary: apt, dnf, pacman, etc.\n"
    )


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------
def get_normalized_path(path: str) -> str:
    """Convert a path to use forward slashes regardless of OS.

    This is useful when passing paths to tools or LLMs that expect
    Unix-style paths, while still being valid on Windows (Python and
    most Windows tools accept forward slashes).
    """
    return path.replace("\\", "/")
