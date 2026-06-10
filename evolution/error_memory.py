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
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger("evocoder.evolution.error_memory")


# ---------------------------------------------------------------------------
# Type-safe data structures
# ---------------------------------------------------------------------------

@dataclass
class ErrorEntry:
    """A single recorded error with full context."""
    id: int
    timestamp: str
    task: str
    error_type: str
    error_msg: str
    attempted_solution: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    resolved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ErrorEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PitfallHint:
    """A fix suggestion derived from past error patterns."""
    error_type: str
    error_msg: str
    attempted_solution: str
    confidence: float
    fix_suggestion: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PitfallSummary:
    """Aggregate statistics on recurring error patterns."""
    total_errors: int
    unresolved: int
    error_breakdown: Dict[str, int]
    most_common_type: Optional[str]
    recent_pitfalls: List[str]
    tips: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


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
                    raw = json.load(f)
                # Support both legacy dict format and new ErrorEntry format
                self.errors = []
                for item in raw:
                    if isinstance(item, dict):
                        self.errors.append(ErrorEntry.from_dict(item))
                    else:
                        self.errors.append(item)
            except (json.JSONDecodeError, IOError):
                self.errors = []

    def _save(self):
        """Persist the full error history to disk as pretty-printed JSON."""
        data = [e.to_dict() if hasattr(e, 'to_dict') else e for e in self.errors]
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

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
        code_snippet: Optional[str] = None,
        fix_applied: Optional[str] = None,
    ) -> ErrorEntry:
        """Record a failure for future reference.

        Args:
            task: Description of what was being attempted.
            error_msg: The error message or traceback text.
            attempted_solution: What was tried that did not work.
            file_path: Optional file where the error occurred.
            line_number: Optional line number of the error.
            code_snippet: Optional code that caused the error.
            fix_applied: Optional fix that resolved the error.

        Returns:
            The newly created ErrorEntry.
        """
        error_type = self._classify_error(error_msg)
        entry = ErrorEntry(
            id=len(self.errors) + 1,
            timestamp=datetime.now().isoformat(),
            task=task,
            error_type=error_type,
            error_msg=error_msg,
            attempted_solution=attempted_solution,
            file_path=file_path,
            line_number=line_number,
            resolved=False,
        )
        self.errors.append(entry)
        self._save()
        return entry

    def suggest_fix(self, error_msg: str) -> List[PitfallHint]:
        """Suggest fixes based on similar past errors.

        Scoring uses three signals:
          - error type match (weight 3.0)
          - keyword overlap (weight 0.5 per shared keyword)
          - substring containment (weight 2.0)

        Args:
            error_msg: The current error message to find matches for.

        Returns:
            Up to 5 best-matching PitfallHint objects, ordered by relevance.
        """
        error_type = self._classify_error(error_msg)
        keywords = self._extract_keywords(error_msg)

        scored_matches: list[tuple[float, ErrorEntry]] = []
        for entry in self.errors:
            entry_msg = entry.error_msg if hasattr(entry, 'error_msg') else entry.get("error_msg", "")
            entry_type = entry.error_type if hasattr(entry, 'error_type') else entry.get("error_type", "")

            score = 0.0
            # Same error type gets high weight
            if entry_type == error_type:
                score += 3.0
            # Keyword overlap
            entry_keywords = self._extract_keywords(entry_msg)
            overlap = keywords & entry_keywords
            if overlap:
                score += len(overlap) * 0.5
            # Partial message similarity
            if error_msg.lower() in entry_msg.lower() or entry_msg.lower() in error_msg.lower():
                score += 2.0

            if score > 0:
                scored_matches.append((score, entry))

        scored_matches.sort(key=lambda x: x[0], reverse=True)

        hints = []
        for score, entry in scored_matches[:5]:
            entry_type = entry.error_type if hasattr(entry, 'error_type') else entry.get("error_type", "")
            entry_msg = entry.error_msg if hasattr(entry, 'error_msg') else entry.get("error_msg", "")
            entry_solution = entry.attempted_solution if hasattr(entry, 'attempted_solution') else entry.get("attempted_solution", "")

            confidence = min(1.0, score / 5.0)
            hint = PitfallHint(
                error_type=entry_type,
                error_msg=entry_msg,
                attempted_solution=entry_solution,
                confidence=round(confidence, 2),
                fix_suggestion=self._generate_fix_suggestion(entry_type, entry_msg),
            )
            hints.append(hint)
        return hints

    def get_pitfall_summary(self) -> PitfallSummary:
        """Generate a summary of common pitfalls from error history.

        Returns:
            PitfallSummary with error_type counts, most common issues,
            and actionable tips for the most frequent error categories.
        """
        if not self.errors:
            return PitfallSummary(
                total_errors=0, unresolved=0, error_breakdown={},
                most_common_type=None, recent_pitfalls=[], tips=[],
            )

        type_counts: dict[str, int] = {}
        failed_tasks: list[str] = []

        for entry in self.errors:
            etype = entry.error_type if hasattr(entry, 'error_type') else entry.get("error_type", "Unknown")
            resolved = entry.resolved if hasattr(entry, 'resolved') else entry.get("resolved", False)
            task = entry.task if hasattr(entry, 'task') else entry.get("task", "")

            type_counts[etype] = type_counts.get(etype, 0) + 1
            if not resolved:
                failed_tasks.append(task)

        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

        return PitfallSummary(
            total_errors=len(self.errors),
            unresolved=len(failed_tasks),
            error_breakdown=dict(sorted_types),
            most_common_type=sorted_types[0][0] if sorted_types else None,
            recent_pitfalls=failed_tasks[-5:] if failed_tasks else [],
            tips=self._generate_tips(type_counts),
        )

    def mark_resolved(self, error_id: int) -> bool:
        """Mark an error as resolved by its ID.

        Returns:
            True if the entry was found and updated, False otherwise.
        """
        for entry in self.errors:
            eid = entry.id if hasattr(entry, 'id') else entry.get("id")
            if eid == error_id:
                if hasattr(entry, 'resolved'):
                    entry.resolved = True
                else:
                    entry["resolved"] = True
                self._save()
                return True
        return False

    def _generate_fix_suggestion(self, error_type: str, error_msg: str) -> str:
        """Generate an actionable fix suggestion based on error type and message."""
        fix_map = {
            "SyntaxError": "Check for missing colons, unmatched brackets, or invalid syntax near the error line.",
            "TypeError": "Verify variable types match expected function signatures. Use isinstance() for type checking.",
            "NameError": "Ensure the variable is defined before use. Check for typos and import statements.",
            "ImportError": "Install the missing package with pip. Verify the module path is correct.",
            "KeyError": "Use dict.get(key, default) or check 'key in dict' before access.",
            "IndexError": "Validate list length before indexing. Use try/except or bounds checking.",
            "FileNotFoundError": "Verify the file path exists. Use os.path.exists() or pathlib.Path.exists().",
            "PermissionError": "Check file permissions. Run with appropriate privileges.",
            "TimeoutError": "Increase timeout value or add retry logic with exponential backoff.",
            "NetworkError": "Add connection retry logic. Check network connectivity and DNS resolution.",
            "MemoryError": "Process data in chunks/generators instead of loading everything into memory.",
            "ValueError": "Validate input data before processing. Check for empty strings, None values, etc.",
            "AttributeError": "Check if the object has the expected attribute. Use hasattr() for safety.",
        }
        suggestion = fix_map.get(error_type, "")
        if not suggestion:
            # Try to extract a hint from the error message itself
            if "did you mean" in error_msg.lower():
                suggestion = "Check the spelling — Python suggests a similar name."
            elif "unexpected" in error_msg.lower():
                suggestion = "Review the syntax around the unexpected token."
            else:
                suggestion = f"Review the error context: {error_msg[:100]}"
        return suggestion

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
