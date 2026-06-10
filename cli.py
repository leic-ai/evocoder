#!/usr/bin/env python3
"""EvoCoder CLI"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

# Fix Windows encoding issues (must be before any print/import)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    "brew": "dim bright_white",
    "token": "dim cyan",
    "cache_hit": "green",
    "cache_miss": "yellow",
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
        t2.add_column("Avg Duration", justify="right")
        for cat, s in strat.items():
            sr = s.get("success_rate", 0)
            sr_style = "green" if sr >= 0.8 else "yellow" if sr >= 0.6 else "red"
            t2.add_row(cat, str(s.get("total_tasks", 0)),
                       f"[{sr_style}]{sr:.0%}[/{sr_style}]",
                       f"{s.get('avg_duration', 0):.1f}s")
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
    stats = agent.long_term.summary()
    console.print(box_title("LONG-TERM MEMORY", "bold bright_green"))

    t = Table(box=box.ROUNDED, border_style="bright_green",
              show_header=False, padding=(0, 2))
    t.add_column("Metric", style="bold")
    t.add_column("Value")
    t.add_row("User", stats["user"]["name"] or "Anonymous")
    t.add_row("Visit Count", str(stats["user"]["visit_count"]))
    t.add_row("Sessions", str(stats["sessions"]["total"]))
    t.add_row("Learned Facts", str(stats["learned"]["total_facts"]))
    console.print(t)

    tags = stats["user"].get("tags", [])
    if tags:
        console.print(f"  [dim]╭──[/dim] [bright_green]Tags: {', '.join(tags)}[/bright_green] [dim]──╮[/dim]")

    console.print(box_subtitle("─" * 20))


def cmd_pitfalls(agent):
    summary = agent.error_memory.get_pitfall_summary()
    console.print(box_title("KNOWN PITFALLS", "bold red"))
    if summary.total_errors == 0:
        console.print(f"  [dim]│[/dim]  No known pitfalls yet. Keep going!")
        console.print(box_subtitle("─" * 20))
        return

    t = Table(box=box.ROUNDED, border_style="red",
              title="[bold red]⚠ Pitfalls ⚠[/bold red]",
              title_style="bold", padding=(0, 2))
    t.add_column("Error Type", style="bold red")
    t.add_column("Count", justify="right")
    for etype, count in summary.error_breakdown.items():
        t.add_row(etype, str(count))
    console.print(t)

    tips = summary.tips
    if tips:
        console.print(f"  [dim]╭──[/dim] [yellow]Tips[/yellow] [dim]──╮[/dim]")
        for tip in tips[:3]:
            console.print(f"  [dim]│[/dim]  {tip}")
    console.print(box_subtitle("─" * 20))


def cmd_prefs(agent):
    prefs = agent.user_prefs.prefs
    console.print(box_title("LEARNED PREFERENCES", "bold bright_cyan"))

    t = Table(box=box.ROUNDED, border_style="bright_cyan",
              show_header=False, padding=(0, 2))
    t.add_column("Setting", style="bold")
    t.add_column("Value")
    t.add_row("Tasks Processed", str(prefs.get("task_count", 0)))
    t.add_row("Language", prefs.get("language", "python"))
    t.add_row("Indent", prefs.get("indent_style", "spaces"))
    t.add_row("Quotes", prefs.get("quote_style", "double"))
    t.add_row("Verbosity", prefs.get("verbosity", "medium"))
    for cat, libs in prefs.get("preferred_libraries", {}).items():
        if libs:
            top = max(libs, key=libs.get) if isinstance(libs, dict) else str(libs)
            t.add_row(f"Lib: {cat}", f"{top}")
    console.print(t)

    if prefs.get("positive_patterns"):
        console.print(f"  [dim]╭──[/dim] [success][+] Positive patterns[/success] [dim]──╮[/dim]")
        for p in prefs["positive_patterns"][-5:]:
            console.print(f"  [dim]│[/dim]      {p}")
    if prefs.get("negative_patterns"):
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


def cmd_search(agent, query: str):
    """Search the web."""
    if not query:
        console.print("  [warning]Usage: /search <query>[/warning]")
        return
    console.print(f"  [info]Searching: {query}[/info]")
    result = agent.registry.execute("web_search", {"query": query, "max_results": 5})
    console.print(Panel(result, title="[info]Search Results[/info]", border_style="cyan"))


def cmd_fetch(agent, url: str):
    """Fetch a web page."""
    if not url:
        console.print("  [warning]Usage: /fetch <url>[/warning]")
        return
    console.print(f"  [info]Fetching: {url}[/info]")
    result = agent.registry.execute("web_fetch", {"url": url})
    console.print(Panel(result[:2000], title="[info]Page Content[/info]", border_style="cyan"))


def cmd_sdd(agent, arg: str):
    """SDD requirement flow."""
    if not arg:
        console.print("  [info]SDD Commands:[/info]")
        console.print("    /sdd new <description>  — Create requirement draft")
        console.print("    /sdd list               — List requirements")
        console.print("    /sdd plans              — List plans")
        return

    parts = arg.split(maxsplit=1)
    subcmd = parts[0].lower()
    detail = parts[1] if len(parts) > 1 else ""

    if subcmd == "new" and detail:
        draft = agent.sdd.create_draft(detail)
        console.print(f"  [success]Draft created: {draft['id']}[/success]")
    elif subcmd == "list":
        reqs = agent.sdd.list_requirements()
        if reqs:
            for r in reqs:
                console.print(f"  • {r['id']}: {r.get('title', 'Untitled')} [{r['status']}]")
        else:
            console.print("  [dim]No requirements yet.[/dim]")
    elif subcmd == "plans":
        plans = agent.sdd.list_plans()
        if plans:
            for p in plans:
                console.print(f"  • {p['id']}: [{p['status']}]")
        else:
            console.print("  [dim]No plans yet.[/dim]")
    else:
        console.print("  [warning]Usage: /sdd new|list|plans [description][/warning]")


def cmd_token(agent):
    """Show token cache statistics and billing."""
    stats = agent.brain.token_cache.get_stats()
    console.print(box_title("TOKEN CACHE & BILLING", "bold bright_cyan"))

    # Cache stats
    t = Table(box=box.ROUNDED, border_style="bright_cyan", show_header=False, padding=(0, 2))
    t.add_column("Metric", style="bold")
    t.add_column("Value", justify="right")
    t.add_row("Cache Hits", str(stats["cache_hits"]))
    t.add_row("Cache Misses", str(stats["cache_misses"]))
    t.add_row("Hit Rate", f"{stats['hit_rate']:.1%}")
    t.add_row("Input Tokens", f"{stats['total_input_tokens']:,}")
    t.add_row("Output Tokens", f"{stats['total_output_tokens']:,}")
    t.add_row("Saved Tokens", f"{stats['saved_tokens']:,}")
    console.print(t)

    # Billing (DeepSeek V4 Pro pricing)
    input_cost = stats['total_input_tokens'] * 2 / 1_000_000  # ¥2/M tokens
    output_cost = stats['total_output_tokens'] * 8 / 1_000_000  # ¥8/M tokens
    cache_saved = stats['cache_hits'] * 1.5 / 1_000_000  # ¥1.5/M saved
    total_cost = input_cost + output_cost - cache_saved

    t2 = Table(box=box.ROUNDED, border_style="bright_green", show_header=False, padding=(0, 2))
    t2.add_column("Item", style="bold")
    t2.add_column("Cost", justify="right")
    t2.add_row("Input Cost", f"¥{input_cost:.4f}")
    t2.add_row("Output Cost", f"¥{output_cost:.4f}")
    t2.add_row("Cache Saved", f"-¥{cache_saved:.4f}")
    t2.add_row("Total Cost", f"¥{total_cost:.4f}")
    console.print(t2)
    console.print(box_subtitle("─" * 20))


def _print_brewed_footer(agent, elapsed: float):
    """Print Claude Code style 'Brewed' footer with timing and token stats."""
    # Format elapsed time
    if elapsed < 1:
        time_str = f"{elapsed:.1f}s"
    elif elapsed < 60:
        time_str = f"{elapsed:.0f}s"
    else:
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        time_str = f"{mins}m{secs}s"

    # Get token stats
    try:
        token_stats = agent.brain.token_cache.get_stats()
        cache_hits = token_stats.get("cache_hits", 0)
        cache_misses = token_stats.get("cache_misses", 0)
        total_input = token_stats.get("total_input_tokens", 0)
        total_output = token_stats.get("total_output_tokens", 0)
        hit_rate = token_stats.get("hit_rate", 0)

        # Format token counts
        if total_input > 1000:
            input_str = f"{total_input/1000:.1f}k"
        else:
            input_str = str(total_input)

        if total_output > 1000:
            output_str = f"{total_output/1000:.1f}k"
        else:
            output_str = str(total_output)

        # Build footer using markup string (avoids append_text issues)
        if cache_hits > 0:
            cache_part = f"[green]{cache_hits} hits[/green] [dim]({hit_rate:.0%})[/dim]"
        else:
            cache_part = f"[yellow]{cache_misses} misses[/yellow]"

        footer_str = (
            f"  [bright_white]*[/bright_white] "
            f"[brew]Brewed for {time_str}[/brew]"
            f"  [dim]|[/dim]  "
            f"[token]{input_str} in / {output_str} out[/token]"
            f"  [dim]|[/dim]  "
            f"[dim]Cache:[/dim] {cache_part}"
        )

        console.print()
        console.print(footer_str)
    except Exception:
        # Fallback if token stats not available
        console.print()
        console.print(f"  [bright_white]*[/bright_white] [brew]Brewed for {time_str}[/brew]")


def cmd_scoreboard(agent):
    """Show tool performance scoreboard."""
    report = agent.scoreboard.report()
    console.print(box_title("TOOL SCOREBOARD", "bold bright_green"))

    if report["total_tools"] == 0:
        console.print(f"  [dim]│[/dim]  No tool usage recorded yet.")
        console.print(box_subtitle("─" * 20))
        return

    t = Table(box=box.ROUNDED, border_style="bright_green",
              title="[bold bright_green]Tool Performance[/bold bright_green]",
              title_style="bold", padding=(0, 2))
    t.add_column("Tool", style="bold")
    t.add_column("Calls", justify="right")
    t.add_column("Success", justify="right")
    t.add_column("Avg ms", justify="right")
    t.add_column("Score", justify="right")

    for tool in report["tools"]:
        sr = tool["success_rate"]
        sr_style = "green" if sr >= 0.8 else "yellow" if sr >= 0.6 else "red"
        score = tool["composite_score"]
        score_style = "green" if score >= 0.7 else "yellow" if score >= 0.5 else "red"
        t.add_row(
            tool["tool_name"],
            str(tool["total_calls"]),
            f"[{sr_style}]{sr:.0%}[/{sr_style}]",
            f"{tool['avg_duration_ms']:.0f}",
            f"[{score_style}]{score:.2f}[/{score_style}]",
        )
    console.print(t)

    under = report.get("underperforming", [])
    if under:
        console.print(f"  [dim]╭──[/dim] [red]Underperforming[/red] [dim]──╮[/dim]")
        for u in under:
            console.print(f"  [dim]│[/dim]  {u['tool_name']}: {u['success_rate']:.0%} success, score={u['composite_score']:.2f}")

    console.print(box_subtitle("─" * 20))


def cmd_help():
    console.print(box_title("HELP", "bold bright_cyan"))
    commands = [
        ("/help", "Show this help"),
        ("/tools", "List available tools"),
        ("/scoreboard", "Tool performance scores"),
        ("/stats", "View statistics & success rates"),
        ("/evolve", "Evolution system status"),
        ("/evolve tools", "View evolved tools"),
        ("/evolve <cat>", "View category evolution"),
        ("/search <query>", "Search the web"),
        ("/fetch <url>", "Fetch web page content"),
        ("/sdd <cmd>", "SDD requirement flow"),
        ("/token", "Token cache statistics"),
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
    try:
        _main()
    except KeyboardInterrupt:
        print("\nBye!")
    except Exception as e:
        import traceback
        crash_log = traceback.format_exc()
        print(f"\nFatal error: {type(e).__name__}: {e}")

        # Write crash log to file for diagnosis
        try:
            log_path = Path(".evocoder") / "crash.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*60}\n")
                f.write(crash_log)
                f.write("\n")
            print(f"Crash log saved to: {log_path}")
        except Exception:
            traceback.print_exc()

        print("\nYour data is saved. Restart with: python cli.py")


def _main():
    parser = argparse.ArgumentParser(description="EvoCoder - Self-Evolving Programming Agent")
    parser.add_argument("--api-key", help="DeepSeek API key")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--workspace", default=".evocoder", help="Workspace directory")
    args = parser.parse_args()

    # Load API key
    api_key = args.api_key or os.getenv("MIMO_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("MIMO_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        except ImportError:
            pass

    if not api_key:
        console.print("[error]Error: No API key found. Set MIMO_API_KEY or DEEPSEEK_API_KEY, or use --api-key[/error]")
        sys.exit(1)

    # Initialize
    print_banner()
    agent = EvoCoder(api_key=api_key, model=args.model, workspace=args.workspace)

    console.print(f"\n  [success]EvoCoder ready![/success] Type your task or /help for commands.\n")

    # REPL — never exits on error, only on /quit or Ctrl+C
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

            try:
                if cmd == "/quit" or cmd == "/exit" or cmd == "/q":
                    console.print("  [info]Bye![/info]")
                    break
                elif cmd == "/help" or cmd == "/h":
                    cmd_help()
                elif cmd == "/tools":
                    cmd_tools(agent)
                elif cmd == "/stats":
                    cmd_stats(agent)
                elif cmd == "/scoreboard":
                    cmd_scoreboard(agent)
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
                elif cmd == "/search":
                    cmd_search(agent, arg)
                elif cmd == "/fetch":
                    cmd_fetch(agent, arg)
                elif cmd == "/sdd":
                    cmd_sdd(agent, arg)
                elif cmd == "/token":
                    cmd_token(agent)
                elif cmd == "/name":
                    if arg:
                        agent.long_term.update_user(name=arg)
                        agent.long_term.save_all()
                        console.print(f"  [success]Nice to meet you, {arg}![/success]")
                    else:
                        console.print("  [warning]Usage: /name <your_name>[/warning]")
                elif cmd == "/feedback":
                    if arg in ("+", "positive", "good"):
                        agent.user_prefs.learn_from_feedback("positive feedback - user is satisfied with the output")
                        console.print("  [success]Thanks! Reinforcing positive patterns.[/success]")
                    elif arg in ("-", "negative", "bad"):
                        agent.user_prefs.learn_from_feedback("negative feedback - user wants different approach")
                        console.print("  [info]Noted. Will avoid this pattern.[/info]")
                    else:
                        console.print("  [warning]Usage: /feedback +/-[/warning]")
                elif cmd == "/clear":
                    agent.memory.clear_conversation()
                    agent.memory.clear_working()
                    console.print("  [info]Session cleared.[/info]")
                else:
                    console.print(f"  [warning]Unknown command: {cmd}. Type /help for commands.[/warning]")
            except Exception as cmd_err:
                console.print(f"  [error]Command error: {type(cmd_err).__name__}: {cmd_err}[/error]")
            continue

        # Run agent with true token-level streaming
        try:
            from agent_events import EventType
            console.print()
            start_time = time.time()
            final_result = ""
            _streaming_content = False  # Track if we're in a streaming content block

            for event in agent.run_stream(user_input):
                try:
                    if event.type == EventType.THINKING:
                        if _streaming_content:
                            console.print("[/agent]", highlight=False)
                            _streaming_content = False
                        console.print(f"  [dim]Step {event.step}...[/dim]", highlight=False)

                    elif event.type == EventType.CONTENT_TOKEN:
                        # Real-time token streaming via Rich console (not raw stdout)
                        token = event.data.get("token", "")
                        if not _streaming_content:
                            console.print("  [agent]", end="", highlight=False)
                            _streaming_content = True
                        # Use Rich console for consistent output
                        console.out(token, end="", highlight=False)

                    elif event.type == EventType.CONTENT:
                        text = event.data.get("text", "")
                        final_result = text
                        if _streaming_content:
                            console.print("[/agent]", highlight=False)
                            _streaming_content = False

                    elif event.type == EventType.TOOL_CALL:
                        if _streaming_content:
                            console.print("[/agent]", highlight=False)
                            _streaming_content = False
                        name = event.data.get("name", "?")
                        args = event.data.get("args", {})
                        args_str = json.dumps(args, ensure_ascii=False)[:80]
                        console.print(f"\n  [tool]>> {name}({args_str})[/tool]", highlight=False)

                    elif event.type == EventType.TOOL_RESULT:
                        name = event.data.get("name", "?")
                        result_text = event.data.get("result", "")
                        is_err = event.data.get("is_error", False)
                        style = "error" if is_err else "dim"
                        console.print(f"  [tool]-> [{style}] {result_text[:120]}[/tool]", highlight=False)

                    elif event.type == EventType.PITFALL_WARNING:
                        etype = event.data.get("error_type", "?")
                        hint = event.data.get("hint", "")
                        console.print(f"  [warning]! Pitfall: {etype} -> {hint[:80]}[/warning]", highlight=False)

                    elif event.type == EventType.EVOLUTION:
                        cat = event.data.get("category", "?")
                        action = event.data.get("action", "")
                        console.print(f"  [evolve]Evolution [{cat}]: {action}[/evolve]", highlight=False)

                    elif event.type == EventType.ERROR:
                        msg = event.data.get("message", "Unknown error")
                        console.print(f"\n  [error]ERROR: {msg}[/error]", highlight=False)

                    elif event.type == EventType.SUMMARY:
                        if _streaming_content:
                            console.print("[/agent]", highlight=False)
                            _streaming_content = False
                        final_result = event.data.get("result", final_result)
                        success = event.data.get("success", False)
                        total_time = event.data.get("total_time", 0)

                        # Print result panel
                    console.print()
                    console.print(Panel(final_result,
                                        border_style="bright_cyan", padding=(1, 2)))

                    # Brewed footer
                    _print_brewed_footer(agent, total_time)

                except Exception as event_err:
                    # Per-event error: log but don't crash the loop
                    if _streaming_content:
                        console.print("[/agent]", highlight=False)
                        _streaming_content = False
                    console.print(f"\n  [error]Event error: {type(event_err).__name__}: {event_err}[/error]", highlight=False)

        except KeyboardInterrupt:
            if _streaming_content:
                console.print("[/agent]", highlight=False)
            console.print("\n  [warning]Interrupted.[/warning]")
        except Exception as e:
            if _streaming_content:
                console.print("[/agent]", highlight=False)
            console.print(f"\n  [error]Error: {type(e).__name__}: {e}[/error]")
            # Don't crash — continue the REPL
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
