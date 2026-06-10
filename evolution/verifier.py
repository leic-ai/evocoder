"""
EvolutionVerifier — Closes the self-evolution loop.

The missing piece: after any evolution (prompt rewrite, strategy change,
tool forge), verify whether it actually improved performance. If not,
roll it back.

Works with:
  - PromptEvolver: compare success rate before/after prompt change
  - ToolForge: compare new tool vs old tool on same task type
  - StrategyMemory: verify strategy changes improved outcomes

Usage:
    verifier = EvolutionVerifier(tracker, prompt_evolver, scoreboard)

    # Before evolution: snapshot current performance
    verifier.snapshot("prompt_rewrite")

    # ... run tasks ...

    # After evolution: verify improvement
    result = verifier.verify("prompt_rewrite")
    # -> {"improved": True, "before": 0.6, "after": 0.8, "action": "keep"}
    # -> {"improved": False, "before": 0.7, "after": 0.5, "action": "rollback"}
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("evocoder.evolution.verifier")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PerformanceSnapshot:
    """A snapshot of performance metrics at a point in time."""
    label: str
    timestamp: float
    success_rate: float
    total_tasks: int
    success_count: int
    failure_count: int
    avg_duration: float = 0.0
    tool_scores: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "timestamp": self.timestamp,
            "success_rate": self.success_rate,
            "total_tasks": self.total_tasks,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_duration": self.avg_duration,
            "tool_scores": self.tool_scores,
            "metadata": self.metadata,
        }


@dataclass
class VerificationResult:
    """Result of comparing before/after performance."""
    label: str
    improved: bool
    before: PerformanceSnapshot
    after: PerformanceSnapshot
    action: str  # "keep", "rollback", "inconclusive"
    reason: str
    delta_success_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "improved": self.improved,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "action": self.action,
            "reason": self.reason,
            "delta_success_rate": round(self.delta_success_rate, 3),
        }


# ---------------------------------------------------------------------------
# EvolutionVerifier
# ---------------------------------------------------------------------------

class EvolutionVerifier:
    """Verifies that evolution changes actually improve performance.

    Takes snapshots before and after evolution, compares success rates,
    and recommends keep/rollback.
    """

    def __init__(
        self,
        tracker: Any = None,
        prompt_evolver: Any = None,
        scoreboard: Any = None,
        strategy_memory: Any = None,
        data_dir: str = ".evocoder/evolution",
        min_tasks_for_verification: int = 5,
        improvement_threshold: float = 0.05,  # 5% improvement to be "better"
        rollback_threshold: float = -0.10,    # 10% worse = rollback
    ):
        self.tracker = tracker
        self.prompt_evolver = prompt_evolver
        self.scoreboard = scoreboard
        self.strategy_memory = strategy_memory

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.min_tasks = min_tasks_for_verification
        self.improvement_threshold = improvement_threshold
        self.rollback_threshold = rollback_threshold

        # Active snapshots: label -> PerformanceSnapshot
        self._snapshots: Dict[str, PerformanceSnapshot] = {}
        self._history: List[VerificationResult] = []

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def snapshot(self, label: str) -> PerformanceSnapshot:
        """Take a performance snapshot before an evolution change.

        Args:
            label: A unique label for this snapshot (e.g. "prompt_v3", "forge_filter_csv").

        Returns:
            The PerformanceSnapshot taken.
        """
        now = time.time()
        success_rate, total, success, failure, avg_dur = self._get_current_performance()

        # Snapshot tool scores if available
        tool_scores = {}
        if self.scoreboard and hasattr(self.scoreboard, '_scores'):
            for name, score in self.scoreboard._scores.items():
                tool_scores[name] = score.composite_score

        snap = PerformanceSnapshot(
            label=label,
            timestamp=now,
            success_rate=success_rate,
            total_tasks=total,
            success_count=success,
            failure_count=failure,
            avg_duration=avg_dur,
            tool_scores=tool_scores,
        )

        self._snapshots[label] = snap
        self._save()

        logger.info(
            "Snapshot '%s': success_rate=%.1f%%, tasks=%d",
            label, success_rate * 100, total,
        )
        return snap

    def verify(self, label: str) -> VerificationResult:
        """Verify whether performance improved since the snapshot.

        Should be called after running enough tasks post-evolution.

        Args:
            label: The label of the snapshot to compare against.

        Returns:
            VerificationResult with keep/rollback recommendation.
        """
        if label not in self._snapshots:
            return VerificationResult(
                label=label,
                improved=False,
                before=PerformanceSnapshot(label="none", timestamp=0, success_rate=0, total_tasks=0, success_count=0, failure_count=0),
                after=PerformanceSnapshot(label="none", timestamp=0, success_rate=0, total_tasks=0, success_count=0, failure_count=0),
                action="inconclusive",
                reason=f"No snapshot found with label '{label}'",
            )

        before = self._snapshots[label]
        now = time.time()
        after_rate, after_total, after_success, after_failure, after_dur = self._get_current_performance()

        # Need minimum tasks since snapshot
        tasks_since = after_total - before.total_tasks
        if tasks_since < self.min_tasks:
            return VerificationResult(
                label=label,
                improved=False,
                before=before,
                after=PerformanceSnapshot(
                    label=f"{label}_after", timestamp=now,
                    success_rate=after_rate, total_tasks=after_total,
                    success_count=after_success, failure_count=after_failure,
                    avg_duration=after_dur,
                ),
                action="inconclusive",
                reason=f"Not enough tasks since snapshot ({tasks_since} < {self.min_tasks})",
            )

        # Calculate success rate after the snapshot
        new_tasks = after_total - before.total_tasks
        new_successes = after_success - before.success_count
        after_snapshot_rate = new_successes / new_tasks if new_tasks > 0 else 0

        after_snap = PerformanceSnapshot(
            label=f"{label}_after", timestamp=now,
            success_rate=after_snapshot_rate,
            total_tasks=new_tasks,
            success_count=new_successes,
            failure_count=new_tasks - new_successes,
            avg_duration=after_dur,
        )

        delta = after_snapshot_rate - before.success_rate

        # Decision
        if delta >= self.improvement_threshold:
            action = "keep"
            improved = True
            reason = f"Performance improved: {before.success_rate:.1%} → {after_snapshot_rate:.1%} (+{delta:.1%})"
        elif delta <= self.rollback_threshold:
            action = "rollback"
            improved = False
            reason = f"Performance degraded: {before.success_rate:.1%} → {after_snapshot_rate:.1%} ({delta:.1%})"
        else:
            action = "inconclusive"
            improved = delta > 0
            reason = f"Marginal change: {before.success_rate:.1%} → {after_snapshot_rate:.1%} ({delta:+.1%})"

        result = VerificationResult(
            label=label,
            improved=improved,
            before=before,
            after=after_snap,
            action=action,
            reason=reason,
            delta_success_rate=delta,
        )

        self._history.append(result)
        self._save()

        logger.info("Verification '%s': %s (delta=%+.1f%%)", label, action, delta * 100)
        return result

    def auto_rollback(self, label: str) -> bool:
        """Auto-rollback a failed evolution.

        Rolls back:
          - PromptEvolver to previous version (if applicable)
          - Strategy changes (if tracked)

        Returns:
            True if rollback was performed.
        """
        result = self.verify(label)
        if result.action != "rollback":
            return False

        rolled_back = False

        # Rollback prompt evolution
        if self.prompt_evolver and label.startswith("prompt_"):
            try:
                self.prompt_evolver.rollback(steps=1)
                logger.info("Rolled back prompt evolution for '%s'", label)
                rolled_back = True
            except Exception as exc:
                logger.warning("Failed to rollback prompt: %s", exc)

        return rolled_back

    def get_history(self) -> List[Dict[str, Any]]:
        """Get verification history."""
        return [r.to_dict() for r in self._history]

    def get_pending_verifications(self) -> List[str]:
        """Get snapshot labels that haven't been verified yet."""
        verified = {r.label for r in self._history}
        return [label for label in self._snapshots if label not in verified]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_current_performance(self) -> tuple:
        """Get current performance metrics from tracker.

        Returns:
            (success_rate, total, success, failure, avg_duration)
        """
        if not self.tracker:
            return 0.0, 0, 0, 0, 0.0

        try:
            summary = self.tracker.summary() if hasattr(self.tracker, 'summary') else {}
            categories = summary.get("categories", {})

            total = 0
            success = 0
            failure = 0
            total_dur = 0.0
            dur_count = 0

            for cat_data in categories.values():
                if isinstance(cat_data, dict):
                    total += cat_data.get("total_tasks", 0)
                    success += cat_data.get("success_count", 0)
                    failure += cat_data.get("failure_count", 0)
                    d = cat_data.get("total_duration", 0)
                    c = cat_data.get("completed_tasks", 0)
                    if d and c:
                        total_dur += d
                        dur_count += c

            rate = success / total if total > 0 else 0.0
            avg_dur = total_dur / dur_count if dur_count > 0 else 0.0

            return rate, total, success, failure, avg_dur

        except Exception:
            return 0.0, 0, 0, 0, 0.0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self):
        data = {
            "snapshots": {k: v.to_dict() for k, v in self._snapshots.items()},
            "history": [r.to_dict() for r in self._history[-50:]],
            "updated_at": time.time(),
        }
        path = self.data_dir / "verifier.json"
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load(self):
        path = self.data_dir / "verifier.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for k, v in data.get("snapshots", {}).items():
                self._snapshots[k] = PerformanceSnapshot(**v)
            # History is just for reference, don't need to fully reconstruct
        except (json.JSONDecodeError, OSError):
            pass
