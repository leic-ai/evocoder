#!/usr/bin/env python3
"""EvoCoder CLI — ╭── 圆角复古终端风格 ──╮"""

import os
import sys
import json
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.text import Text
from rich.theme import Theme
from rich import box
from rich.align import Align

from agent import EvoCoder

# ── 自定义主题 ──
theme = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "user": "bold bright_green",
    "agent": "bold bright_cyan",
    "tool": "dim cyan",
    "evolve": "bold magenta",
})

console = Console(theme=theme)

# ── 边框宽度 ──
W = 72


def box_title(text, style="bold bright_cyan"):
    return f"  [dim]╭──[/dim] [{style}]{text}[/] [dim]──╮[/dim]"


def box_subtitle(text, style="dim"):
    return f"  [dim]╰──[/dim] [{style}]{text}[/] [dim]──╯[/dim]"


def print_banner():
    from evo_splash import show_splash
    show_splash()


def cmd_tools(agent):
    tools = agent.registry.list_tools()
    console.print(box_title("TOOLS", "bold bright_cyan"))
    if not tools:
        console.print(f"  [dim]│[/dim]  (no tools)")
        console.print(box_subtitle("─" * 20))
        return
    t = Table(box=box.ROUNDED, border_style="bright_cyan",
              show_header=True, header_style="bold bright_cyan",
              padding=(0, 2))
    t.add_column("Name", style="bold")
    t.add_column("Category", style="dim")
    t.add_column("Calls", justify="right")
    t.add_column("Success", justify="right")
    for tool in tools:
        rate = tool["success_rate"]
        rate_style = "green" if "100" in rate or "9" in rate else "yellow" if "8" in rate or "7" in rate else "red"
        t.add_row(tool["name"], tool["category"], str(tool["calls"]),
                  f"[{rate_style}]{rate}[/{rate_style}]")
    console.print(t)
    console.print(box_subtitle("─" * 20))


def cmd_stats(agent):
    stats = agent.get_stats()
    console.print(box_title("STATS", "bold bright_cyan"))

    t = Table(box=box.ROUNDED, border_style="bright_cyan", show_header=False, padding=(0, 2))
    t.add_column("Metric", style="bold")
    t.add_column("Value", justify="right")
    rate = stats["success_rate"]
    rate_style = "green" if rate >= 0.8 else "yellow" if rate >= 0.6 else "red"
    t.add_row("Tools", str(len(stats["tools"])))
    t.add_row("Experiences", str(stats["total_experiences"]))
    t.add_row("Success Rate", f"[{rate_style}]{rate:.0%}[/{rate_style}]")
    t.add_row("Pitfalls Known", str(stats["pitfall_count"]))
    t.add_row("User Tasks", str(stats["user_task_count"]))
    console.print(Panel(t, title="[bold]Overview[/]", border_style="bright_cyan"))

    strat = stats.get("strategy_stats", {})
    if strat:
        t2 = Table(box=box.ROUNDED, border_style="bright_cyan",
                   title="[bold bright_cyan]Strategy Stats[/bold bright_cyan]",
                   title_style="bold", padding=(0, 2))
        t2.add_column("Category", style="bold")
        t2.add_column("Tasks", justify="right")
        t2.add_column("Success", justify="right")
        t2.add_column("Avg Steps", justify="right")
        t2.add_column("Top Tools")
        for cat, s in strat.items():
            tools_str = ", ".join(t[0] for t in s.get("top_tools", []))
            sr = s["success_rate"]
            sr_style = "green" if sr >= 0.8 else "yellow" if sr >= 0.6 else "red"
            t2.add_row(cat, str(s["total"]),
                       f"[{sr_style}]{sr:.0%}[/{sr_style}]",
                       str(s["avg_iterations"]), tools_str)
        console.print(t2)

    # Sub-agent stats
    sub_stats = stats.get("subagent_stats", {})
    if sub_stats and sub_stats.get("total_calls", 0) > 0:
        t3 = Table(box=box.ROUNDED, border_style="bright_green",
                   title="[bold bright_green]Sub-Agent Stats[/bold bright_green]",
                   title_style="bold", padding=(0, 2))
        t3.add_column("Type", style="bold")
        t3.add_column("Calls", justify="right")
        t3.add_column("Success", justify="right")
        for name, data in sub_stats.get("by_type", {}).items():
            total = data.get("total", 0)
            success = data.get("success", 0)
            sr = success / total if total > 0 else 0
            sr_style = "green" if sr >= 0.8 else "yellow" if sr >= 0.6 else "red"
            t3.add_row(name, str(total), f"[{sr_style}]{sr:.0%}[/{sr_style}]")
        console.print(t3)

    console.print(box_subtitle("─" * 20))


def cmd_evolve(agent, arg: str = ""):
    status = agent.get_evolution_status()
    console.print(box_title("EVOLUTION", "bold magenta"))

    if arg and arg.strip().lower() == "tools":
        tools = agent.tool_evolver.list_evolved_tools()
        if not tools:
            console.print(f"  [dim]│[/dim]  No evolved tools yet.")
            console.print(box_subtitle("─" * 20))
            return
        t = Table(box=box.ROUNDED, border_style="bright_green",
                  title="[bold bright_green]Evolved Tools[/bold bright_green]",
                  title_style="bold", padding=(0, 2))
        t.add_column("Name", style="bold")
        t.add_column("Description")
        t.add_column("Status")
        t.add_column("Created")
        for tool in tools:
            import time
            st = tool["status"]
            color = {"active": "green", "inactive": "dim"}.get(st, "dim")
            created = time.strftime("%Y-%m-%d %H:%M", time.localtime(tool["created_at"]))
            t.add_row(tool["name"], tool["description"][:40],
                      f"[{color}]{st}[/{color}]", created)
        console.print(t)
        console.print(box_subtitle("─" * 20))
        return

    if arg:
        cat = arg.strip().lower()
        if cat not in status:
            console.print(f"  [dim]│[/dim]  Unknown category: {cat}")
            console.print(box_subtitle("─" * 20))
            return
        history = agent.evolver.get_evolution_history(cat)
        if not history:
            console.print(f"  [dim]│[/dim]  No evolution history for [{cat}]")
            console.print(box_subtitle("─" * 20))
            return
        t = Table(box=box.ROUNDED, border_style="magenta",
                  title=f"[bold magenta]Evolution: {cat}[/bold magenta]",
                  title_style="bold", padding=(0, 2))
        t.add_column("Ver", style="bold")
        t.add_column("Status")
        t.add_column("Confidence", justify="right")
        t.add_column("Failures", justify="right")
        t.add_column("Analysis")
        for h in history:
            st = h["status"]
            color = {"accepted": "green", "rejected": "red", "pending": "yellow"}.get(st, "dim")
            t.add_row(f"v{h['version']}", f"[{color}]{st}[/{color}]",
                      f"{h['confidence']:.0%}", str(h["failure_count"]),
                      h["analysis"][:50] if h["analysis"] else "")
        console.print(t)
        console.print(box_subtitle("─" * 20))
        return

    t = Table(box=box.ROUNDED, border_style="magenta",
              title="[bold magenta]Evolution Status[/bold magenta]",
              title_style="bold", padding=(0, 2))
    t.add_column("Category", style="bold")
    t.add_column("Versions", justify="right")
    t.add_column("Evolved")
    t.add_column("Strategy")
    t.add_column("Tasks", justify="right")
    t.add_column("Success", justify="right")
    for cat, info in status.items():
        evolved = "[green]YES[/green]" if info["has_evolved"] else "[dim]-[/dim]"
        sr = info["success_rate"]
        sr_style = "green" if sr >= 0.8 else "yellow" if sr >= 0.6 else "red"
        t.add_row(cat, str(info["versions"]), evolved,
                  info["strategy"], str(info["total_tasks"]),
                  f"[{sr_style}]{sr:.0%}[/{sr_style}]")
    console.print(t)
    console.print(box_subtitle("─" * 20))


def cmd_memory(agent):
    stats = agent.long_term.get_stats()
    console.print(box_title("LONG-TERM MEMORY", "bold bright_green"))

    t = Table(box=box.ROUNDED, border_style="bright_green",
              show_header=False, padding=(0, 2))
    t.add_column("Metric", style="bold")
    t.add_column("Value")
    t.add_row("User", stats["user_name"])
    t.add_row("Total Tasks", str(stats["task_count"]))
    t.add_row("Sessions", str(stats["session_count"]))
    t.add_row("Topics", str(stats["topic_count"]))
    t.add_row("Learned Patterns", str(stats["pattern_count"]))
    t.add_row("Memorable Moments", str(stats["moment_count"]))
    console.print(t)

    tags = agent.long_term.user.get("tags", [])
    if tags:
        console.print(f"  [dim]╭──[/dim] [bright_green]Tags: {', '.join(tags)}[/bright_green] [dim]──╮[/dim]")

    topics = agent.long_term.history.get("topics", {})
    if topics:
        top_topics = sorted(topics.items(), key=lambda x: -x[1])[:5]
        topics_str = ", ".join(f"{t[0]}({t[1]})" for t in top_topics)
        console.print(f"  [dim]╭──[/dim] Topics: {topics_str} [dim]──╮[/dim]")

    console.print(box_subtitle("─" * 20))


def cmd_pitfalls(agent):
    pitfalls = agent.error_memory.get_common_pitfalls(10)
    console.print(box_title("KNOWN PITFALLS", "bold red"))
    if not pitfalls:
        console.print(f"  [dim]│[/dim]  No known pitfalls yet. Keep going!")
        console.print(box_subtitle("─" * 20))
        return
    t = Table(box=box.ROUNDED, border_style="red",
              title="[bold red]⚠ Pitfalls ⚠[/bold red]",
              title_style="bold", padding=(0, 2))
    t.add_column("Error", style="bold red")
    t.add_column("Feature")
    t.add_column("Fix")
    t.add_column("Hits", justify="right")
    for p in pitfalls:
        t.add_row(p["error_type"], p["code_feature"][:35],
                  p["fix_applied"][:50], str(p["hit_count"]))
    console.print(t)
    console.print(box_subtitle("─" * 20))


def cmd_prefs(agent):
    prefs = agent.user_prefs.prefs
    console.print(box_title("LEARNED PREFERENCES", "bold bright_cyan"))

    t = Table(box=box.ROUNDED, border_style="bright_cyan",
              show_header=False, padding=(0, 2))
    t.add_column("Setting", style="bold")
    t.add_column("Value")
    t.add_row("Tasks Processed", str(prefs["task_count"]))
    t.add_row("Language", prefs["language"])
    t.add_row("Indent", prefs["code_style"]["indent"])
    t.add_row("Quotes", prefs["code_style"]["quotes"])
    t.add_row("Verbosity", prefs["verbosity"])
    for cat, libs in prefs["lib_preferences"].items():
        if libs:
            top = max(libs, key=libs.get)
            t.add_row(f"Lib: {cat}", f"{top} ({libs[top]}x)")
    console.print(t)

    if prefs["positive_patterns"]:
        console.print(f"  [dim]╭──[/dim] [success][+] Positive patterns[/success] [dim]──╮[/dim]")
        for p in prefs["positive_patterns"][-5:]:
            console.print(f"  [dim]│[/dim]      {p}")
    if prefs["negative_patterns"]:
        console.print(f"  [dim]╭──[/dim] [error][-] Negative patterns[/error] [dim]──╮[/dim]")
        for p in prefs["negative_patterns"][-5:]:
            console.print(f"  [dim]│[/dim]      {p}")

    console.print(box_subtitle("─" * 20))


def cmd_subagents(agent):
    types = agent.subagents.list_types()
    console.print(box_title("SUBAGENTS", "bold bright_green"))

    t = Table(box=box.ROUNDED, border_style="bright_green",
              show_header=True, header_style="bold bright_green",
              padding=(0, 2))
    t.add_column("Type", style="bold")
    t.add_column("Name")
    t.add_column("Tools", justify="right")
    t.add_column("Max Iter", justify="right")

    for item in types:
        t.add_row(item["name"], item["description"][:40],
                  str(item.get("tools_count", "?")), str(item.get("max_iterations", "?")))
    console.print(t)
    console.print(box_subtitle("─" * 20))


def cmd_help():
    console.print(box_title("HELP", "bold bright_cyan"))
    commands = [
        ("/help", "Show this help"),
        ("/tools", "List available tools"),
        ("/stats", "View statistics & success rates"),
        ("/evolve", "Evolution system status"),
        ("/evolve tools", "View evolved tools"),
        ("/evolve <cat>", "View category evolution"),
        ("/memory", "Long-term memory stats"),
        ("/pitfalls", "Known error patterns"),
        ("/prefs", "Learned preferences"),
        ("/subagents", "Sub-agent types"),
        ("/name <name>", "Set your name"),
        ("/feedback +/-", "Rate last result"),
        ("/clear", "Clear session"),
        ("/quit", "Exit EvoCoder"),
    ]
    t = Table(box=box.ROUNDED, border_style="bright_cyan", show_header=False, padding=(0, 2))
    t.add_column("Command", style="bold")
    t.add_column("Description")
    for cmd, desc in commands:
        t.add_row(cmd, desc)
    console.print(t)
    console.print(box_subtitle("─" * 20))


def main():
    parser = argparse.ArgumentParser(description="EvoCoder - Self-Evolving Programming Agent")
    parser.add_argument("--api-key", help="DeepSeek API key")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--workspace", default=".evocoder", help="Workspace directory")
    args = parser.parse_args()

    # Load API key
    api_key = args.api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("DEEPSEEK_API_KEY")
        except ImportError:
            pass

    if not api_key:
        console.print("[error]Error: No API key found. Set DEEPSEEK_API_KEY or use --api-key[/error]")
        sys.exit(1)

    # Initialize
    print_banner()
    agent = EvoCoder(api_key=api_key, model=args.model, workspace=args.workspace)

    console.print(f"\n  [success]EvoCoder ready![/success] Type your task or /help for commands.\n")

    # REPL
    while True:
        try:
            user_input = console.input("[user]> [/user]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n  [info]Bye! 🐳[/info]")
            break

        if not user_input:
            continue

        # Commands
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "/quit" or cmd == "/exit" or cmd == "/q":
                console.print("  [info]Bye! 🐳[/info]")
                break
            elif cmd == "/help" or cmd == "/h":
                cmd_help()
            elif cmd == "/tools":
                cmd_tools(agent)
            elif cmd == "/stats":
                cmd_stats(agent)
            elif cmd == "/evolve":
                cmd_evolve(agent, arg)
            elif cmd == "/memory":
                cmd_memory(agent)
            elif cmd == "/pitfalls":
                cmd_pitfalls(agent)
            elif cmd == "/prefs":
                cmd_prefs(agent)
            elif cmd == "/subagents":
                cmd_subagents(agent)
            elif cmd == "/name":
                if arg:
                    agent.long_term.update_user(name=arg)
                    agent.long_term.save_all()
                    console.print(f"  [success]Nice to meet you, {arg}! 🐳[/success]")
                else:
                    console.print("  [warning]Usage: /name <your_name>[/warning]")
            elif cmd == "/feedback":
                if arg in ("+", "positive", "good"):
                    agent.user_prefs.learn_from_feedback("", "", True)
                    console.print("  [success]Thanks! Reinforcing positive patterns.[/success]")
                elif arg in ("-", "negative", "bad"):
                    agent.user_prefs.learn_from_feedback("", "", False)
                    console.print("  [info]Noted. Will avoid this pattern.[/info]")
                else:
                    console.print("  [warning]Usage: /feedback +/-[/warning]")
            elif cmd == "/clear":
                agent.memory.clear_session()
                console.print("  [info]Session cleared.[/info]")
            else:
                console.print(f"  [warning]Unknown command: {cmd}. Type /help for commands.[/warning]")
            continue

        # Run agent
        try:
            console.print()
            result = agent.run(user_input)
            console.print()
            console.print(Panel(result, title="[agent]🤖 EvoCoder[/agent]",
                                border_style="bright_cyan", padding=(1, 2)))
        except KeyboardInterrupt:
            console.print("\n  [warning]Interrupted.[/warning]")
        except Exception as e:
            console.print(f"\n  [error]Error: {type(e).__name__}: {e}[/error]")


if __name__ == "__main__":
    main()
