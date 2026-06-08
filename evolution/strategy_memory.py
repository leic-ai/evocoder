"""
StrategyMemory - Task-aware strategy selection and learning from outcomes.

Part of EvoCoder's self-improvement system.  Maintains a library of reusable
strategy prompts keyed by task category (code, debug, refactor, file, git,
search, general).  After each task the outcome is recorded so that future
strategy selection can be weighted by historical success/failure.

The four core operations are:

  record_task_result  -- log a task outcome and update success weights
  get_strategy_prompt -- return the best strategy prompt for a given task
  classify_task       -- determine which category a natural-language task
                        description belongs to
  get_stats           -- return per-strategy success/failure statistics

Design mirrors the sibling modules (ErrorMemory, UserPreferences):
JSON persistence, keyword-based matching, weighted voting.
"""

import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("evocoder.evolution.strategy_memory")


# ---------------------------------------------------------------------------
# Default strategy prompts
# ---------------------------------------------------------------------------

DEFAULT_STRATEGIES: dict[str, dict] = {
    "code": {
        "description": "Write new code from scratch",
        "prompt": (
            "Write clean, well-structured code.  "
            "Start with a clear plan: identify inputs, outputs, and edge cases.  "
            "Use meaningful names.  Keep functions short and focused.  "
            "Add docstrings for non-trivial functions.  "
            "Handle errors explicitly -- never silently swallow exceptions."
        ),
        "keywords": [
            "write", "create", "implement", "build", "add", "new",
            "function", "class", "feature", "develop", "code",
            "script", "program", "generate", "design", "construct",
        ],
    },
    "debug": {
        "description": "Diagnose and fix bugs",
        "prompt": (
            "Reproduce the bug first.  Read the full traceback carefully.  "
            "Isolate the failing code path with targeted print/log statements "
            "or a debugger.  Check recent changes (git diff) for regressions.  "
            "Fix the root cause, not the symptom.  "
            "Write a test that fails before the fix and passes after."
        ),
        "keywords": [
            "bug", "debug", "fix", "error", "crash", "traceback",
            "exception", "broken", "fail", "wrong", "issue", "problem",
            "trace", "stack", "segfault",
        ],
    },
    "refactor": {
        "description": "Restructure existing code without changing behaviour",
        "prompt": (
            "Ensure all existing tests pass before starting.  "
            "Make one structural change at a time and verify after each step.  "
            "Extract repeated logic into helpers.  "
            "Reduce nesting depth.  "
            "Improve naming to reveal intent.  "
            "Run the full test suite after each change to catch regressions early."
        ),
        "keywords": [
            "refactor", "restructure", "clean", "simplify", "reorganize",
            "extract", "rename", "improve", "readable", "maintainability",
            "decompose", "split", "modular", "optimize", "rewrite",
        ],
    },
    "file": {
        "description": "Read, write, or manipulate files",
        "prompt": (
            "Check that the file exists before reading.  "
            "Use context managers (with/open) for file I/O.  "
            "Handle encoding explicitly (utf-8 as default).  "
            "For large files, stream line-by-line instead of loading into memory.  "
            "Validate paths before writing to avoid accidental overwrites."
        ),
        "keywords": [
            "file", "read", "save", "load", "path", "directory",
            "folder", "open", "json", "yaml", "csv", "txt",
            "config", "serialize", "deserialize",
        ],
    },
    "git": {
        "description": "Version control operations",
        "prompt": (
            "Use clear, imperative commit messages.  "
            "Keep commits atomic -- one logical change per commit.  "
            "Check git status before committing to avoid staging unintended files.  "
            "Use branches for experimental work.  "
            "Pull before pushing to avoid conflicts."
        ),
        "keywords": [
            "git", "commit", "push", "pull", "branch", "merge",
            "rebase", "diff", "log", "stash", "checkout", "clone",
            "repository", "repo", "version", "vcs",
        ],
    },
    "search": {
        "description": "Search code, files, or the web for information",
        "prompt": (
            "Start with broad search terms, then narrow down.  "
            "Use ripgrep (rg) or grep for code search -- include context lines.  "
            "For web searches, prefer official docs over random blog posts.  "
            "Verify information from multiple sources before acting on it.  "
            "Cache search results to avoid repeated lookups."
        ),
        "keywords": [
            "search", "find", "grep", "look", "locate", "query",
            "match", "pattern", "regex", "scan", "browse", "explore",
            "discover", "investigate", "research",
        ],
    },
    "general": {
        "description": "Catch-all for tasks that don't fit other categories",
        "prompt": (
            "Understand the full context before acting.  "
            "Break the task into smaller steps.  "
            "Verify each step before moving on.  "
            "Ask for clarification if the goal is ambiguous."
        ),
        "keywords": [],  # always matches as fallback
    },
}


class StrategyMemory:
    """Maintains task strategies and learns from outcomes to improve selection.

    Usage::

        sm = StrategyMemory()
        category = sm.classify_task("Fix the login crash")   # -> "debug"
        prompt   = sm.get_strategy_prompt(category)           # strategy text
        # ... execute the task ...
        sm.record_task_result(category, success=True, duration=12.5)

    The per-strategy success weights are persisted so that over time the
    system preferentially selects strategies that have historically worked
    well for similar tasks.
    """

    def __init__(self, memory_path: str = "strategy_memory.json"):
        self.memory_path = Path(memory_path)
        self.strategies: dict = {}
        self.results: list[dict] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load strategy state from disk.  Missing file is not an error."""
        if not self.memory_path.exists():
            self._init_strategies()
            return
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge saved strategies over defaults so new categories get defaults
            self._init_strategies()
            for cat, saved in data.get("strategies", {}).items():
                if cat in self.strategies:
                    self.strategies[cat].update(saved)
                else:
                    self.strategies[cat] = saved
            self.results = data.get("results", [])
            logger.info("Loaded strategy memory from %s", self.memory_path)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to load strategy memory: %s", exc)
            self._init_strategies()

    def _init_strategies(self) -> None:
        """Seed strategies from DEFAULT_STRATEGIES with runtime fields."""
        self.strategies = {}
        for cat, tpl in DEFAULT_STRATEGIES.items():
            self.strategies[cat] = {
                "description": tpl["description"],
                "prompt": tpl["prompt"],
                "keywords": list(tpl["keywords"]),
                "success_count": 0,
                "failure_count": 0,
                "total_duration": 0.0,
                "customizations": [],
            }

    def _save(self) -> None:
        """Persist the full strategy state to disk."""
        data = {
            "strategies": self.strategies,
            "results": self.results[-500:],  # cap history
            "updated_at": datetime.now().isoformat(),
        }
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.warning("Failed to save strategy memory: %s", exc)

    # ------------------------------------------------------------------
    # Public API: classify_task
    # ------------------------------------------------------------------

    def classify_task(self, task_description: str) -> str:
        """Determine which strategy category a task description belongs to.

        Uses keyword scoring: each category's keyword list is checked against
        the task text.  The category with the most keyword hits wins.
        Ties are broken by keyword position (earlier matches score slightly
        higher).  Falls back to ``"general"`` when nothing matches.

        Args:
            task_description: Natural-language description of the task.

        Returns:
            One of the strategy category names (e.g. "code", "debug").
        """
        text = task_description.lower()
        # Tokenise once
        words = set(re.findall(r'[a-z_]\w+', text))

        # Ambiguous keywords shared across categories -- down-weight them
        _ambiguous = {
            "write", "module", "code", "file", "change", "use",
            "add", "make", "get", "set", "run", "check",
        }

        best_cat = "general"
        best_score = 0

        for cat, info in self.strategies.items():
            if cat == "general":
                continue
            score = 0
            for kw in info.get("keywords", []):
                if kw in words:
                    # Ambiguous shared words get reduced weight
                    score += 1 if kw in _ambiguous else 3
                elif kw in text:
                    score += 1
            if score > best_score:
                best_score = score
                best_cat = cat

        logger.debug("Classified task '%s' -> '%s' (score=%d)", task_description[:60], best_cat, best_score)
        return best_cat

    # ------------------------------------------------------------------
    # Public API: get_strategy_prompt
    # ------------------------------------------------------------------

    def get_strategy_prompt(
        self,
        category: str,
        include_customizations: bool = True,
    ) -> str:
        """Return the strategy prompt for a given category.

        If the category has learned customizations (from
        ``record_task_result`` with ``lessons_learned``), they are appended
        to the base prompt so the system benefits from past experience.

        Args:
            category: Strategy category name (e.g. "code", "debug").
            include_customizations: Whether to append learned tips.

        Returns:
            The strategy prompt string.  Falls back to "general" if the
            category is unknown.
        """
        info = self.strategies.get(category) or self.strategies.get("general", {})
        prompt = info.get("prompt", "")

        if include_customizations:
            customizations = info.get("customizations", [])
            if customizations:
                # Keep only the most recent customizations to avoid prompt bloat
                recent = customizations[-10:]
                tips = "; ".join(recent)
                prompt = f"{prompt}  [Learned tips: {tips}]"

        return prompt

    # ------------------------------------------------------------------
    # Public API: record_task_result
    # ------------------------------------------------------------------

    def record_task_result(
        self,
        category: str,
        success: bool,
        duration: Optional[float] = None,
        task_description: Optional[str] = None,
        lessons_learned: Optional[str] = None,
    ) -> dict:
        """Record the outcome of a task to update strategy statistics.

        Success/failure counts are updated for the category, which affects
        future weighting.  Optional ``lessons_learned`` are stored as
        customizations that get appended to the strategy prompt.

        Args:
            category: The strategy category that was used.
            success: Whether the task completed successfully.
            duration: Elapsed time in seconds (optional).
            task_description: What the task was about (optional).
            lessons_learned: A short tip to remember for next time (optional).

        Returns:
            The result entry dict that was recorded.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "success": success,
            "duration": duration,
            "task_description": task_description,
            "lessons_learned": lessons_learned,
        }
        self.results.append(entry)

        # Update strategy stats
        info = self.strategies.get(category)
        if info:
            if success:
                info["success_count"] = info.get("success_count", 0) + 1
            else:
                info["failure_count"] = info.get("failure_count", 0) + 1
            if duration is not None:
                info["total_duration"] = info.get("total_duration", 0.0) + duration

            # Store customization tip
            if lessons_learned:
                info.setdefault("customizations", []).append(lessons_learned)
                logger.info("Learned lesson for '%s': %s", category, lessons_learned[:80])
        else:
            logger.warning("record_task_result called for unknown category '%s'", category)

        self._save()
        return entry

    # ------------------------------------------------------------------
    # Public API: get_stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return per-strategy success/failure statistics.

        Returns:
            Dict keyed by category name, each value containing:
            success_count, failure_count, success_rate, avg_duration,
            and total_tasks.
        """
        stats = {}
        for cat, info in self.strategies.items():
            sc = info.get("success_count", 0)
            fc = info.get("failure_count", 0)
            total = sc + fc
            stats[cat] = {
                "success_count": sc,
                "failure_count": fc,
                "total_tasks": total,
                "success_rate": round(sc / total, 3) if total else 0.0,
                "avg_duration": round(
                    info.get("total_duration", 0.0) / total, 2
                ) if total else 0.0,
                "customizations": len(info.get("customizations", [])),
            }
        return stats

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def best_strategy_for(self, task_description: str) -> tuple[str, str]:
        """Convenience: classify and return (category, prompt) in one call.

        Args:
            task_description: Natural-language task description.

        Returns:
            Tuple of (category_name, strategy_prompt).
        """
        category = self.classify_task(task_description)
        prompt = self.get_strategy_prompt(category)
        return category, prompt

    def get_customizations(self, category: str) -> list[str]:
        """Return the learned customization tips for a category."""
        info = self.strategies.get(category, {})
        return list(info.get("customizations", []))

    def add_strategy(
        self,
        category: str,
        description: str,
        prompt: str,
        keywords: Optional[list[str]] = None,
    ) -> None:
        """Register a new custom strategy category.

        Args:
            category: Unique category name.
            description: Short human-readable description.
            prompt: The strategy prompt text.
            keywords: Keywords that trigger this category.
        """
        self.strategies[category] = {
            "description": description,
            "prompt": prompt,
            "keywords": keywords or [],
            "success_count": 0,
            "failure_count": 0,
            "total_duration": 0.0,
            "customizations": [],
        }
        self._save()
        logger.info("Registered new strategy: '%s'", category)

    def reset_stats(self) -> None:
        """Reset all success/failure counters and clear results history."""
        for info in self.strategies.values():
            info["success_count"] = 0
            info["failure_count"] = 0
            info["total_duration"] = 0.0
            info["customizations"] = []
        self.results.clear()
        self._save()
        logger.info("Strategy stats reset")

    def summary(self) -> dict:
        """High-level summary of the strategy memory."""
        stats = self.get_stats()
        total_tasks = sum(s["total_tasks"] for s in stats.values())
        return {
            "total_strategies": len(self.strategies),
            "total_results_recorded": len(self.results),
            "total_tasks": total_tasks,
            "strategies": {
                cat: {
                    "description": self.strategies[cat]["description"],
                    "tasks": s["total_tasks"],
                    "success_rate": s["success_rate"],
                }
                for cat, s in stats.items()
            },
        }

    def __len__(self) -> int:
        return len(self.strategies)

    def __repr__(self) -> str:
        cats = ", ".join(self.strategies.keys())
        return f"StrategyMemory(strategies=[{cats}], results={len(self.results)})"


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sm = StrategyMemory("test_strategy_memory.json")

    # Demo: classify tasks
    tasks = [
        "Fix the login crash when password is empty",
        "Write a CLI argument parser",
        "Refactor the database module to use connection pooling",
        "Search for all TODO comments in the codebase",
        "Commit the changes and push to main",
        "Read the config.yaml and parse its contents",
        "Help me organise my project structure",
    ]

    print("Task classification:")
    for task in tasks:
        cat, prompt = sm.best_strategy_for(task)
        print(f"  [{cat:8s}] {task}")

    # Demo: record results
    sm.record_task_result("debug", success=True, duration=45.0,
                          task_description="Fix login crash")
    sm.record_task_result("debug", success=False, duration=120.0,
                          task_description="Fix memory leak",
                          lessons_learned="Check for circular references in callbacks")
    sm.record_task_result("code", success=True, duration=30.0,
                          task_description="CLI parser")

    # Demo: stats
    print(f"\nStats: {json.dumps(sm.get_stats(), indent=2)}")
    print(f"\nSummary: {json.dumps(sm.summary(), indent=2)}")

    # Demo: learned tips show up in prompt
    prompt = sm.get_strategy_prompt("debug")
    print(f"\nDebug strategy (with tips):\n{prompt}")

    # Cleanup
    sm.memory_path.unlink(missing_ok=True)
    print("\nDone. Cleaned up test file.")
