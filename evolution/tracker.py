"""
Evolution Tracker for EvoCoder

Tracks task execution history and determines when the system should
self-evolve based on accumulated experience.  Each task is recorded
with its steps, outcomes, errors, and duration.  Aggregated stats
per category feed into the evolution decision engine.
"""

import time
import uuid
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("evocoder.evolution.tracker")


# ---------------------------------------------------------------------------
# Task status enum
# ---------------------------------------------------------------------------

class TaskStatus(Enum):
    """Possible outcomes for a tracked task."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# TaskRecord dataclass
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    """Immutable record of a single task execution."""

    task_id: str
    category: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    steps: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Timing
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    # Tooling
    tools_used: List[str] = field(default_factory=list)
    tool_calls: int = 0
    tool_failures: int = 0

    # Token / cost (optional, filled by Brain if available)
    tokens_in: int = 0
    tokens_out: int = 0

    # Result
    result: Optional[str] = None

    # ---- derived properties ------------------------------------------------

    @property
    def duration(self) -> Optional[float]:
        """Elapsed seconds, or None if not finished."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.SUCCESS

    # ---- serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "description": self.description,
            "status": self.status.value,
            "steps": self.steps,
            "errors": self.errors,
            "metadata": self.metadata,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "tools_used": self.tools_used,
            "tool_calls": self.tool_calls,
            "tool_failures": self.tool_failures,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        data = dict(data)  # shallow copy
        data["status"] = TaskStatus(data.get("status", "pending"))
        # Remove derived field if present
        data.pop("duration", None)
        return cls(**data)


# ---------------------------------------------------------------------------
# Category statistics
# ---------------------------------------------------------------------------

@dataclass
class CategoryStats:
    """Aggregated statistics for a single task category."""

    category: str
    total_tasks: int = 0
    success_count: int = 0
    failure_count: int = 0
    cancelled_count: int = 0
    total_steps: int = 0
    total_errors: int = 0
    total_duration: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    unique_tools: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.success_count / self.total_tasks

    @property
    def avg_duration(self) -> float:
        completed = self.success_count + self.failure_count
        if completed == 0:
            return 0.0
        return self.total_duration / completed

    @property
    def avg_steps(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_steps / self.total_tasks

    @property
    def error_rate(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return self.total_errors / self.total_steps

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "total_tasks": self.total_tasks,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "cancelled_count": self.cancelled_count,
            "success_rate": round(self.success_rate, 3),
            "avg_duration": round(self.avg_duration, 2),
            "avg_steps": round(self.avg_steps, 1),
            "error_rate": round(self.error_rate, 3),
            "total_steps": self.total_steps,
            "total_errors": self.total_errors,
            "total_duration": round(self.total_duration, 2),
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "unique_tools": self.unique_tools,
        }


# ---------------------------------------------------------------------------
# EvolutionTracker
# ---------------------------------------------------------------------------

class EvolutionTracker:
    """
    Records task executions and determines when self-evolution is needed.

    Responsibilities:
    - Track task lifecycle: start -> log steps -> end
    - Persist task history to disk (JSON Lines format)
    - Compute per-category statistics
    - Decide when accumulated evidence warrants an evolution cycle

    Usage::

        tracker = EvolutionTracker()
        task = tracker.start_task("file_ops", "Refactor config loading")
        tracker.log_step(task.task_id, "Read config.json", {"path": "config.json"})
        tracker.end_task(task.task_id, TaskStatus.SUCCESS, result="Done")
        stats = tracker.get_category_stats()
        if tracker.should_evolve():
            # trigger evolution
    """

    def __init__(
        self,
        history_dir: str = ".evocoder/evolution",
        evolve_threshold_tasks: int = 5,
        evolve_threshold_failure_rate: float = 0.3,
        evolve_threshold_error_rate: float = 0.2,
        max_history: int = 500,
    ):
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)

        # In-memory active tasks (task_id -> TaskRecord)
        self._active: Dict[str, TaskRecord] = {}

        # Completed / finalised records
        self._history: List[TaskRecord] = []

        # Evolution decision thresholds
        self.evolve_threshold_tasks = evolve_threshold_tasks
        self.evolve_threshold_failure_rate = evolve_threshold_failure_rate
        self.evolve_threshold_error_rate = evolve_threshold_error_rate

        self.max_history = max_history

        # Load persisted history on init
        self._load_history()

    # ---- persistence -------------------------------------------------------

    def _history_path(self) -> Path:
        return self.history_dir / "task_history.jsonl"

    def _load_history(self) -> None:
        """Load task records from the JSONL history file."""
        path = self._history_path()
        if not path.exists():
            return
        count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                record = TaskRecord.from_dict(data)
                self._history.append(record)
                count += 1
            except (json.JSONDecodeError, TypeError, KeyError) as exc:
                logger.debug("Skipping malformed history line: %s", exc)
                continue
        logger.info("Loaded %d task records from %s", count, path)

    def _persist_record(self, record: TaskRecord) -> None:
        """Append a single record to the JSONL history file."""
        path = self._history_path()
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to persist task %s: %s", record.task_id, exc)

    def _save_all(self) -> None:
        """Rewrite the full history file (used after pruning)."""
        path = self._history_path()
        try:
            lines = [
                json.dumps(r.to_dict(), ensure_ascii=False)
                for r in self._history[-self.max_history:]
            ]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to rewrite history: %s", exc)

    # ---- task lifecycle ----------------------------------------------------

    def start_task(
        self,
        category: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskRecord:
        """
        Begin tracking a new task.

        Args:
            category: Task category (e.g. "file_ops", "code_gen", "debug").
            description: Human-readable description of what the task does.
            metadata: Optional extra data to attach to the record.

        Returns:
            The newly created TaskRecord (status = RUNNING).
        """
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(
            task_id=task_id,
            category=category,
            description=description,
            status=TaskStatus.RUNNING,
            start_time=time.time(),
            metadata=metadata or {},
        )
        self._active[task_id] = record
        logger.info("Started task [%s] %s: %s", task_id, category, description[:80])
        return record

    def log_step(
        self,
        task_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        *,
        tool: Optional[str] = None,
        is_error: bool = False,
    ) -> None:
        """
        Record a step within an active task.

        Args:
            task_id: The task to log against.
            action: Short description of this step.
            details: Arbitrary detail dict.
            tool: Name of the tool used in this step (if any).
            is_error: If True, this step is also recorded as an error.
        """
        record = self._active.get(task_id)
        if record is None:
            logger.warning("log_step called for unknown task %s", task_id)
            return

        step = {
            "action": action,
            "time": time.time(),
            "details": details or {},
        }
        if tool:
            step["tool"] = tool
            record.tool_calls += 1
            if tool not in record.tools_used:
                record.tools_used.append(tool)

        record.steps.append(step)

        if is_error:
            record.errors.append({
                "action": action,
                "time": time.time(),
                "details": details or {},
            })
            record.tool_failures += 1

        logger.debug("Task [%s] step: %s%s", task_id, action, " (ERROR)" if is_error else "")

    def end_task(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[str] = None,
    ) -> Optional[TaskRecord]:
        """
        Finalise a task and move it to history.

        Args:
            task_id: The task to end.
            status: Final status (SUCCESS, FAILURE, or CANCELLED).
            result: Optional result summary string.

        Returns:
            The finalised TaskRecord, or None if task_id was unknown.
        """
        record = self._active.pop(task_id, None)
        if record is None:
            logger.warning("end_task called for unknown task %s", task_id)
            return None

        record.status = status
        record.end_time = time.time()
        record.result = result

        # Move to history
        self._history.append(record)
        self._persist_record(record)

        # Prune if needed
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
            self._save_all()

        logger.info(
            "Ended task [%s] status=%s duration=%.1fs steps=%d errors=%d",
            task_id, status.value, record.duration or 0, record.step_count, record.error_count,
        )
        return record

    # ---- statistics --------------------------------------------------------

    def get_category_stats(self) -> Dict[str, CategoryStats]:
        """
        Compute aggregated statistics grouped by task category.

        Returns:
            Dict mapping category name -> CategoryStats.
        """
        buckets: Dict[str, CategoryStats] = {}

        for record in self._history:
            cat = record.category
            if cat not in buckets:
                buckets[cat] = CategoryStats(category=cat)
            stats = buckets[cat]

            stats.total_tasks += 1

            if record.status == TaskStatus.SUCCESS:
                stats.success_count += 1
            elif record.status == TaskStatus.FAILURE:
                stats.failure_count += 1
            elif record.status == TaskStatus.CANCELLED:
                stats.cancelled_count += 1

            stats.total_steps += record.step_count
            stats.total_errors += record.error_count

            if record.duration is not None:
                stats.total_duration += record.duration

            stats.total_tokens_in += record.tokens_in
            stats.total_tokens_out += record.tokens_out

            for tool in record.tools_used:
                if tool not in stats.unique_tools:
                    stats.unique_tools.append(tool)

        return buckets

    # ---- evolution decision ------------------------------------------------

    def should_evolve(self) -> bool:
        """
        Decide whether enough evidence has accumulated to trigger evolution.

        Evolution is recommended when ANY of these conditions hold:
        1. At least N tasks recorded AND overall failure rate exceeds threshold.
        2. At least N tasks recorded AND overall step error rate exceeds threshold.
        3. Any single category has >= N tasks with failure rate > threshold.

        Returns:
            True if an evolution cycle should be triggered.
        """
        stats = self.get_category_stats()
        all_categories = list(stats.values())

        if not all_categories:
            return False

        # Aggregate totals
        total_tasks = sum(s.total_tasks for s in all_categories)
        total_failures = sum(s.failure_count for s in all_categories)
        total_steps = sum(s.total_steps for s in all_categories)
        total_errors = sum(s.total_errors for s in all_categories)

        # Not enough data yet
        if total_tasks < self.evolve_threshold_tasks:
            return False

        # Condition 1: global failure rate
        overall_failure_rate = total_failures / total_tasks if total_tasks else 0.0
        if overall_failure_rate > self.evolve_threshold_failure_rate:
            logger.info(
                "Evolve triggered: overall failure rate %.1f%% > %.1f%%",
                overall_failure_rate * 100, self.evolve_threshold_failure_rate * 100,
            )
            return True

        # Condition 2: global error rate (errors per step)
        overall_error_rate = total_errors / total_steps if total_steps else 0.0
        if overall_error_rate > self.evolve_threshold_error_rate:
            logger.info(
                "Evolve triggered: overall error rate %.1f%% > %.1f%%",
                overall_error_rate * 100, self.evolve_threshold_error_rate * 100,
            )
            return True

        # Condition 3: any category hotspot
        for cat_stats in all_categories:
            if cat_stats.total_tasks >= self.evolve_threshold_tasks:
                if cat_stats.failure_rate > self.evolve_threshold_failure_rate:
                    logger.info(
                        "Evolve triggered: category '%s' failure rate %.1f%%",
                        cat_stats.category, cat_stats.failure_rate * 100,
                    )
                    return True

        return False

    # ---- querying ----------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Look up a task by ID (checks active first, then history)."""
        if task_id in self._active:
            return self._active[task_id]
        for record in reversed(self._history):
            if record.task_id == task_id:
                return record
        return None

    def recent_tasks(self, n: int = 10) -> List[TaskRecord]:
        """Return the N most recent completed tasks."""
        return self._history[-n:]

    def failed_tasks(self, n: int = 10) -> List[TaskRecord]:
        """Return up to N most recent failed tasks."""
        failed = [r for r in self._history if r.status == TaskStatus.FAILURE]
        return failed[-n:]

    def active_tasks(self) -> List[TaskRecord]:
        """Return currently running tasks."""
        return list(self._active.values())

    # ---- summary -----------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """High-level tracker summary."""
        cat_stats = self.get_category_stats()
        total = len(self._history)
        successes = sum(1 for r in self._history if r.status == TaskStatus.SUCCESS)
        failures = sum(1 for r in self._history if r.status == TaskStatus.FAILURE)

        return {
            "total_tasks": total,
            "active_tasks": len(self._active),
            "successes": successes,
            "failures": failures,
            "success_rate": round(successes / total, 3) if total else 0.0,
            "categories": {k: v.to_dict() for k, v in cat_stats.items()},
            "should_evolve": self.should_evolve(),
        }

    def __len__(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return (
            f"EvolutionTracker(history={len(self._history)}, "
            f"active={len(self._active)})"
        )
