"""
ToolScoreboard — Performance tracking and adaptive tool selection.

Records every tool invocation's outcome (success/failure, duration, quality)
and uses that history to:
  1. Rank tools by effectiveness for each task category
  2. Surface underperforming tools for refinement
  3. Auto-select the best tool when multiple candidates exist
  4. Provide the LLM with tool performance context

This is the feedback loop that makes forged tools get better over time:
  forge → use → score → refine/retire → repeat
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("evocoder.tools.scoreboard")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolScore:
    """Aggregated performance score for a single tool."""
    tool_name: str
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    quality_scores: List[float] = field(default_factory=list)  # 0.0-1.0
    last_used: float = 0.0
    last_error: str = ""
    categories_used: Dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.success_count / self.total_calls

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls

    @property
    def avg_quality(self) -> float:
        if not self.quality_scores:
            return 0.5  # neutral
        return sum(self.quality_scores) / len(self.quality_scores)

    @property
    def composite_score(self) -> float:
        """Overall score combining success rate, quality, and recency.

        Range: 0.0 (terrible) to 1.0 (excellent).
        """
        if self.total_calls == 0:
            return 0.5  # unknown = neutral

        # Success rate (weight: 0.4)
        sr = self.success_rate * 0.4

        # Quality (weight: 0.4)
        q = self.avg_quality * 0.4

        # Recency bonus (weight: 0.2) — recently used tools get a small boost
        age_hours = (time.time() - self.last_used) / 3600 if self.last_used else 999
        recency = max(0, 1.0 - age_hours / 168) * 0.2  # decays over 1 week

        return sr + q + recency

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "total_calls": self.total_calls,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "avg_quality": round(self.avg_quality, 3),
            "composite_score": round(self.composite_score, 3),
            "last_used": self.last_used,
            "last_error": self.last_error[:100],
            "categories_used": self.categories_used,
        }


@dataclass
class ToolCallRecord:
    """A single tool invocation record for the scoreboard."""
    tool_name: str
    timestamp: float
    success: bool
    duration_ms: float
    category: str = ""
    quality: float = 0.5  # 0.0-1.0, default neutral
    error: str = ""
    task: str = ""


# ---------------------------------------------------------------------------
# ToolScoreboard
# ---------------------------------------------------------------------------

class ToolScoreboard:
    """Tracks tool performance and provides adaptive selection.

    Usage:
        board = ToolScoreboard(data_dir=".evocoder/scoreboard")

        # Record a tool call
        board.record("read_file", success=True, duration_ms=12.5, category="file")

        # Get ranked tools for a task
        best = board.best_tools_for_category("file", top_k=3)
        # -> [("read_file", 0.92), ("list_directory", 0.85), ...]

        # Get performance report
        report = board.report()
    """

    def __init__(self, data_dir: str = ".evocoder/scoreboard"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._scores: Dict[str, ToolScore] = {}
        self._recent_calls: List[ToolCallRecord] = []
        self._max_recent = 500

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float = 0.0,
        category: str = "",
        quality: float = -1.0,
        error: str = "",
        task: str = "",
    ) -> None:
        """Record a tool invocation outcome.

        Args:
            tool_name: Name of the tool.
            success: Whether it succeeded.
            duration_ms: Execution time in milliseconds.
            category: Task category (code, debug, file, etc.).
            quality: Quality score 0.0-1.0. If -1, auto-infer from success.
            error: Error message if failed.
            task: Task description.
        """
        now = time.time()

        # Auto-infer quality if not provided
        if quality < 0:
            quality = 0.8 if success else 0.2

        # Update aggregate scores
        if tool_name not in self._scores:
            self._scores[tool_name] = ToolScore(tool_name=tool_name)

        score = self._scores[tool_name]
        score.total_calls += 1
        if success:
            score.success_count += 1
        else:
            score.failure_count += 1
            score.last_error = error
        score.total_duration_ms += duration_ms
        score.quality_scores.append(quality)
        if len(score.quality_scores) > 100:
            score.quality_scores = score.quality_scores[-100:]
        score.last_used = now
        if category:
            score.categories_used[category] = score.categories_used.get(category, 0) + 1

        # Record in recent calls
        record = ToolCallRecord(
            tool_name=tool_name,
            timestamp=now,
            success=success,
            duration_ms=duration_ms,
            category=category,
            quality=quality,
            error=error,
            task=task[:200],
        )
        self._recent_calls.append(record)
        if len(self._recent_calls) > self._max_recent:
            self._recent_calls = self._recent_calls[-self._max_recent:]

        self._save()

    def get_score(self, tool_name: str) -> Optional[ToolScore]:
        """Get the performance score for a tool."""
        return self._scores.get(tool_name)

    def best_tools_for_category(
        self,
        category: str,
        top_k: int = 5,
        min_calls: int = 2,
    ) -> List[Tuple[str, float]]:
        """Rank tools by effectiveness for a task category.

        Args:
            category: Task category to rank for.
            top_k: Number of top tools to return.
            min_calls: Minimum calls to be considered.

        Returns:
            List of (tool_name, composite_score) tuples, sorted by score descending.
        """
        candidates = []
        for name, score in self._scores.items():
            # Prefer tools that have been used in this category
            cat_count = score.categories_used.get(category, 0)
            if cat_count == 0 and score.total_calls < min_calls:
                continue
            if score.total_calls < min_calls:
                continue

            # Boost score if tool has been used in this category before
            cat_boost = min(0.1, cat_count * 0.02)
            adjusted = score.composite_score + cat_boost
            candidates.append((name, adjusted))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def best_tools_for_task(
        self,
        task_description: str,
        top_k: int = 3,
    ) -> List[Tuple[str, float, str]]:
        """Find best tools for a task description using keyword matching + scores.

        Returns:
            List of (tool_name, score, reason) tuples.
        """
        task_lower = task_description.lower()
        task_words = set(task_lower.split())

        candidates = []
        for name, score in self._scores.items():
            if score.total_calls < 2:
                continue

            # Keyword match between task and tool name/description
            name_words = set(name.lower().replace("_", " ").split())
            overlap = task_words & name_words
            keyword_score = len(overlap) * 0.2

            combined = score.composite_score + keyword_score
            reason = f"score={score.composite_score:.2f}"
            if overlap:
                reason += f", keywords={overlap}"
            candidates.append((name, combined, reason))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def underperforming_tools(
        self,
        threshold: float = 0.4,
        min_calls: int = 5,
    ) -> List[ToolScore]:
        """Find tools with low performance scores that may need refinement.

        Args:
            threshold: Score below this is considered underperforming.
            min_calls: Minimum calls to be evaluated.

        Returns:
            List of underperforming ToolScore objects.
        """
        return [
            score for score in self._scores.values()
            if score.total_calls >= min_calls and score.composite_score < threshold
        ]

    def recently_failed(self, n: int = 10) -> List[ToolCallRecord]:
        """Get the N most recent failed tool calls."""
        failed = [r for r in self._recent_calls if not r.success]
        return failed[-n:]

    def report(self) -> Dict[str, Any]:
        """Generate a performance report for all tools."""
        if not self._scores:
            return {"total_tools": 0, "total_calls": 0, "tools": []}

        tools = sorted(
            self._scores.values(),
            key=lambda s: s.composite_score,
            reverse=True,
        )

        total_calls = sum(s.total_calls for s in tools)
        total_success = sum(s.success_count for s in tools)

        return {
            "total_tools": len(tools),
            "total_calls": total_calls,
            "overall_success_rate": round(total_success / total_calls, 3) if total_calls else 0,
            "tools": [t.to_dict() for t in tools],
            "underperforming": [
                t.to_dict() for t in self.underperforming_tools()
            ],
        }

    def get_context_for_llm(self, category: str = "") -> str:
        """Build a performance context string for the LLM.

        Injected into the system prompt so the LLM knows which tools
        work well and which to avoid.
        """
        if not self._scores:
            return ""

        lines = ["[Tool Performance History]"]

        if category:
            ranked = self.best_tools_for_category(category, top_k=5)
            if ranked:
                lines.append(f"Best tools for '{category}' tasks:")
                for name, score in ranked:
                    s = self._scores[name]
                    lines.append(
                        f"  - {name}: {s.success_rate:.0%} success, "
                        f"{s.avg_duration_ms:.0f}ms avg, "
                        f"score={score:.2f}"
                    )

        # Warn about underperforming tools
        bad = self.underperforming_tools()
        if bad:
            lines.append("Underperforming tools (avoid if possible):")
            for s in bad[:3]:
                lines.append(
                    f"  - {s.tool_name}: {s.success_rate:.0%} success, "
                    f"last error: {s.last_error[:60]}"
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self):
        """Persist scoreboard to disk."""
        data = {
            "scores": {name: s.to_dict() for name, s in self._scores.items()},
            "updated_at": time.time(),
        }
        path = self.data_dir / "scoreboard.json"
        try:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save scoreboard: %s", exc)

    def _load(self):
        """Load scoreboard from disk."""
        path = self.data_dir / "scoreboard.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for name, sdata in data.get("scores", {}).items():
                self._scores[name] = ToolScore(
                    tool_name=sdata["tool_name"],
                    total_calls=sdata.get("total_calls", 0),
                    success_count=sdata.get("success_count", 0),
                    failure_count=sdata.get("failure_count", 0),
                    total_duration_ms=sdata.get("total_duration_ms", 0),
                    quality_scores=sdata.get("quality_scores", []),
                    last_used=sdata.get("last_used", 0),
                    last_error=sdata.get("last_error", ""),
                    categories_used=sdata.get("categories_used", {}),
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load scoreboard: %s", exc)
