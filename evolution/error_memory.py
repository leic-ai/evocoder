"""
ErrorMemory - Tracks past failures and suggests fixes to avoid repeated mistakes.

Part of EvoCoder's self-improvement system.  By recording every error the coder
encounters along with the attempted (and failed) solutions, it builds a growing
knowledge base that prevents the same mistakes from happening twice.

The three core operations are:

  record_failure     -- log a new error with full context
  suggest_fix        -- look up past errors similar to the current one
  get_pitfall_summary -- aggregate statistics on recurring problem patterns
"""

import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class ErrorMemory:
    """Stores error history and provides fix suggestions based on past failures.

    Each error entry captures the task description, the raw error message,
    the solution that was attempted (but failed), and optional location info.
    Over time the accumulated history lets us rank similar errors and surface
    the most relevant past experience to avoid repeating the same mistake.
    """

    def __init__(self, memory_path: str = "error_memory.json"):
        self.memory_path = Path(memory_path)
        self.errors: list[dict] = []
        self._load()

    def _load(self):
        """Load error history from disk.

        If the file does not exist or is corrupted we start with an empty
        history so the system can still operate gracefully.
        """
        if self.memory_path.exists():
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    self.errors = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.errors = []

    def _save(self):
        """Persist the full error history to disk as pretty-printed JSON."""
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(self.errors, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Error classification
    # ------------------------------------------------------------------

    def _classify_error(self, error_msg: str) -> str:
        """Classify error into a type category.

        Checks for known Python exception names in the message text,
        then falls back to a custom tag pattern [ERR:TAG], and finally
        returns 'Unknown' if nothing matches.
        """
        msg = error_msg.lower()

        if "syntaxerror" in msg:
            return "SyntaxError"
        if "typeerror" in msg:
            return "TypeError"
        if "nameerror" in msg:
            return "NameError"
        if "attributeerror" in msg:
            return "AttributeError"
        if "keyerror" in msg:
            return "KeyError"
        if "indexerror" in msg:
            return "IndexError"
        if "importerror" in msg or "modulenotfounderror" in msg:
            return "ImportError"
        if "filenotfounderror" in msg or "no such file" in msg:
            return "FileNotFoundError"
        if "permissionerror" in msg:
            return "PermissionError"
        if "timeout" in msg:
            return "TimeoutError"
        if "connection" in msg or "network" in msg:
            return "NetworkError"
        if "memory" in msg or "overflow" in msg:
            return "MemoryError"
        if "valueerror" in msg:
            return "ValueError"
        # Custom error tag: [ERR:SOME_TAG]
        custom_match = re.search(r'\[ERR:(\w+)\]', error_msg)
        if custom_match:
            return custom_match.group(1)

        return "Unknown"

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract meaningful keywords from error text."""
        stop_words = {
            "the", "a", "an", "is", "in", "on", "at", "to", "for",
            "of", "and", "or", "not", "was", "were", "been", "be",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "can", "shall", "that",
            "this", "it", "from", "with", "by", "as", "but", "if",
        }
        words = re.findall(r'[a-z_]\w+', text.lower())
        return {w for w in words if w not in stop_words and len(w) > 2}

    def record_failure(
        self,
        task: str,
        error_msg: str,
        attempted_solution: str,
        file_path: Optional[str] = None,
        line_number: Optional[int] = None,
    ) -> dict:
        """Record a failure for future reference.

        Args:
            task: Description of what was being attempted.
            error_msg: The error message or traceback text.
            attempted_solution: What was tried that did not work.
            file_path: Optional file where the error occurred.
            line_number: Optional line number of the error.

        Returns:
            The newly created error entry dict.
        """
        error_type = self._classify_error(error_msg)
        entry = {
            "id": len(self.errors) + 1,
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "error_type": error_type,
            "error_msg": error_msg,
            "attempted_solution": attempted_solution,
            "file_path": file_path,
            "line_number": line_number,
            "resolved": False,
        }
        self.errors.append(entry)
        self._save()
        return entry

    def suggest_fix(self, error_msg: str) -> list[dict]:
        """Suggest fixes based on similar past errors.

        Scoring uses three signals:
          - error type match (weight 3.0)
          - keyword overlap (weight 0.5 per shared keyword)
          - substring containment (weight 2.0)

        Args:
            error_msg: The current error message to find matches for.

        Returns:
            Up to 5 best-matching past errors, ordered by relevance.
        """
        error_type = self._classify_error(error_msg)
        keywords = self._extract_keywords(error_msg)

        scored_matches: list[tuple[float, dict]] = []
        for entry in self.errors:
            score = 0.0
            # Same error type gets high weight
            if entry["error_type"] == error_type:
                score += 3.0
            # Keyword overlap
            entry_keywords = self._extract_keywords(entry["error_msg"])
            overlap = keywords & entry_keywords
            if overlap:
                score += len(overlap) * 0.5
            # Partial message similarity
            if error_msg.lower() in entry["error_msg"].lower() or entry["error_msg"].lower() in error_msg.lower():
                score += 2.0

            if score > 0:
                scored_matches.append((score, entry))

        scored_matches.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored_matches[:5]]

    def get_pitfall_summary(self) -> dict:
        """Generate a summary of common pitfalls from error history.

        Returns:
            Dict with error_type counts, most common issues, and
            actionable tips for the most frequent error categories.
        """
        if not self.errors:
            return {"total_errors": 0, "message": "No errors recorded yet."}

        type_counts: dict[str, int] = {}
        failed_tasks: list[str] = []

        for entry in self.errors:
            etype = entry["error_type"]
            type_counts[etype] = type_counts.get(etype, 0) + 1
            if not entry.get("resolved"):
                failed_tasks.append(entry["task"])

        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

        summary = {
            "total_errors": len(self.errors),
            "unresolved": len(failed_tasks),
            "error_breakdown": dict(sorted_types),
            "most_common_type": sorted_types[0][0] if sorted_types else None,
            "recent_pitfalls": failed_tasks[-5:] if failed_tasks else [],
            "tips": self._generate_tips(type_counts),
        }
        return summary

    def mark_resolved(self, error_id: int) -> bool:
        """Mark an error as resolved by its ID.

        Returns:
            True if the entry was found and updated, False otherwise.
        """
        for entry in self.errors:
            if entry["id"] == error_id:
                entry["resolved"] = True
                self._save()
                return True
        return False

    def _generate_tips(self, type_counts: dict[str, int]) -> list[str]:
        """Generate actionable tips based on error patterns."""
        tips = []
        for etype, count in type_counts.items():
            if count < 2:
                continue
            tip_map = {
                "SyntaxError": "Review code syntax before running. Use a linter.",
                "TypeError": "Check variable types and function signatures carefully.",
                "NameError": "Verify all variables are defined before use. Check imports.",
                "ImportError": "Confirm dependencies are installed and module paths are correct.",
                "KeyError": "Use .get() with defaults or check key existence first.",
                "IndexError": "Validate list/array bounds before accessing elements.",
                "FileNotFoundError": "Check file paths and ensure files exist before reading.",
                "NetworkError": "Add retry logic and timeout handling for network calls.",
                "TimeoutError": "Increase timeout values or optimize slow operations.",
            }
            if etype in tip_map:
                tips.append(f"[{etype} x{count}] {tip_map[etype]}")

        if not tips:
            tips.append("Keep recording errors to build up fix suggestions.")
        return tips


if __name__ == "__main__":
    mem = ErrorMemory("test_error_memory.json")

    # Demo: record a failure
    entry = mem.record_failure(
        task="Load config file",
        error_msg="FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'",
        attempted_solution="Used hardcoded path, file was in different directory",
        file_path="main.py",
        line_number=42,
    )
    print(f"Recorded: #{entry['id']}")

    # Demo: suggest fix
    suggestions = mem.suggest_fix("FileNotFoundError: config.json not found")
    print(f"\nSuggestions for current error ({len(suggestions)} matches):")
    for s in suggestions:
        print(f"  #{s['id']} [{s['error_type']}] {s['task']} -> tried: {s['attempted_solution']}")

    # Demo: pitfall summary
    summary = mem.get_pitfall_summary()
    print(f"\nPitfall Summary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # Cleanup
    mem.memory_path.unlink(missing_ok=True)
