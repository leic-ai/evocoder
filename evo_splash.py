"""
Splash screen for EvoCoder — rendered with Rich console.

Features:
  - Whale ASCII art (10 lines of pixel blocks)
  - EVO_LOGO (6 lines of block characters)
  - Animated water wave effect
  - System info bar (Python, OS, model, tools)
  - Command reference table
  - Claude Code style footer

Usage:
    from evo_splash import show_splash
    show_splash()
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.table import Table
    from rich.align import Align
    from rich.columns import Columns
    from rich.rule import Rule
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "0.7.1"

# Whale — 10 lines of Braille / pixel block art
WHALE_ART = [
    "                        ████████████                    ",
    "                  ██████████████████████████              ",
    "              ██████████████████████████████████          ",
    "          ░░██████████████████████████████████████░░      ",
    "        ░░░░████████████████████████████████████████░░    ",
    "  ░░░░░░░░░░████████████████████████████████████████████░░",
    "░░░░░░░░░░░░██████████████████████████████████████████████",
    "  ░░░░░░░░██████████████████████████████████████████████  ",
    "      ░░░░██████████████████████████████████████████      ",
    "          ████████████████████████████████████████        ",
]

# EVO logo — 6 lines of solid block characters
EVO_LOGO = [
    "███████  ██    ██  ██████ ",
    "██       ██    ██ ██      ",
    "█████    ██    ██ ██   ███",
    "██        ██  ██  ██    ██",
    "███████   ████    ██████  ",
    "                           ",
]

# Water wave tiles (3 variations for animation frames)
WAVE_TILES = [
    "▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀",
    "▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄",
    "▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀▄▀",
]

# Command palette
COMMANDS = [
    ("/help",      "Show all commands",            "white"),
    ("/ask",       "Ask a question",               "white"),
    ("/code",      "Generate code",                "white"),
    ("/debug",     "Debug an error",               "white"),
    ("/file",      "Read / write / edit files",    "white"),
    ("/git",       "Git operations",               "white"),
    ("/search",    "Web search",                   "white"),
    ("/tools",     "List registered tools",        "white"),
    ("/brain",     "Brain diagnostics",            "white"),
    ("/evolve",    "View evolution stats",         "white"),
    ("/clear",     "Clear conversation",           "white"),
    ("/quit",      "Exit EvoCoder",                "white"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_system_info() -> dict:
    """Collect system metadata for the info bar."""
    info = {
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cwd": str(Path.cwd()),
    }
    # Try to load model from config
    try:
        import json as _json
        cfg_path = Path(__file__).resolve().parent / "config.json"
        if cfg_path.exists():
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            api_cfg = cfg.get("api", {})
            info["model"] = api_cfg.get("model", "deepseek-chat")
            info["base_url"] = api_cfg.get("base_url", "https://api.deepseek.com")
        else:
            info["model"] = "deepseek-chat"
            info["base_url"] = "https://api.deepseek.com"
    except Exception:
        info["model"] = "unknown"
        info["base_url"] = "unknown"
    return info


def _count_tools() -> int:
    """Count registered tools (lazy import to avoid circular deps)."""
    try:
        from tools.registry import ToolRegistry
        from tools.builtin import register_builtins
        reg = ToolRegistry()
        register_builtins(reg)
        return len(reg)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_whale(console: Console) -> None:
    """Print the whale ASCII art in cyan/blue gradient."""
    for i, line in enumerate(WHALE_ART):
        # Gradient: deeper blue at top, lighter toward water
        if i < 3:
            color = "bright_cyan"
        elif i < 6:
            color = "cyan"
        else:
            color = "blue"
        console.print(f"  {line}", style=f"bold {color}")


def _render_logo(console: Console) -> None:
    """Print EVO_LOGO block characters in green with 'coder' suffix."""
    for i, line in enumerate(EVO_LOGO):
        # Last two lines: append "coder" label
        if i == 0:
            suffix = "  [bright_white]CODER[/bright_white]"
        elif i == 4:
            suffix = f"  [dim]v{VERSION}[/dim]"
        else:
            suffix = ""
        # Color the logo blocks
        if i < 3:
            color = "bright_green"
        else:
            color = "green"
        console.print(f"  [{color}]{line}[/{color}]{suffix}")


def _render_waves(console: Console, frame: int = 0) -> None:
    """Print water waves (3 layers for depth)."""
    tile = WAVE_TILES[frame % len(WAVE_TILES)]
    console.print(f"  [bright_blue]{tile}[/bright_blue]")
    console.print(f"  [blue]{tile}[/blue]")
    console.print(f"  [dim blue]{tile}[/dim blue]")


def _render_system_info(console: Console) -> None:
    """Print the system info bar."""
    info = _get_system_info()
    tool_count = _count_tools()

    parts = [
        f"[bright_cyan]Python[/bright_cyan] [white]{info['python']}[/white]",
        f"[bright_cyan]OS[/bright_cyan] [white]{info['os']}[/white]",
        f"[bright_cyan]Model[/bright_cyan] [bright_yellow]{info['model']}[/bright_yellow]",
        f"[bright_cyan]Tools[/bright_cyan] [bright_green]{tool_count}[/bright_green]",
        f"[bright_cyan]Time[/bright_cyan] [dim]{info['time']}[/dim]",
    ]

    bar = "  [dim]|[/dim] ".join(parts)
    console.print(f"\n  {bar}\n")
    console.print(
        f"  [dim]CWD: {info['cwd']}[/dim]"
    )


def _render_commands(console: Console) -> None:
    """Print the command reference table in Claude Code style."""
    table = Table(
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 2, 0, 0),
        expand=False,
    )
    table.add_column("Command", style="bright_yellow", min_width=10)
    table.add_column("Description", style="white")

    for cmd, desc, _ in COMMANDS:
        table.add_row(cmd, desc)

    console.print()
    console.print(
        Panel(
            table,
            title="[bold bright_white]Commands[/bold bright_white]",
            border_style="bright_blue",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def _render_footer(console: Console) -> None:
    """Print Claude Code style footer."""
    console.print()
    console.print(
        Rule(
            title="[dim]powered by DeepSeek | self-evolving agent framework[/dim]",
            style="bright_blue",
            characters="─",
        )
    )
    footer_text = Text()
    footer_text.append("  EvoCoder", style="bold bright_green")
    footer_text.append(f" v{VERSION}", style="dim")
    footer_text.append("  |  ", style="dim")
    footer_text.append("Type a command or just describe what you need.", style="dim")
    footer_text.append("  |  ", style="dim")
    footer_text.append("Ctrl+C to exit", style="dim")
    console.print(footer_text)
    console.print()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show_splash(
    console: Optional[Console] = None,
) -> None:
    """
    Render the EvoCoder splash screen.

    Args:
        console: Rich Console instance. Creates a new one if None.
    """
    # Force UTF-8 on Windows to avoid GBK encoding errors with Unicode blocks
    if sys.platform == "win32":
        os.system("")  # enable VT100 escape codes
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if console is None:
        console = Console(force_terminal=True)

    console.clear()

    # Whale art
    _render_whale(console)

    # Gap between whale and logo
    console.print()

    # EVO logo
    _render_logo(console)

    # Waves — three layers for depth effect
    _render_waves(console, 0)

    # System info
    _render_system_info(console)

    # Commands
    _render_commands(console)

    # Footer
    _render_footer(console)


# ---------------------------------------------------------------------------
# Standalone entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    show_splash()
