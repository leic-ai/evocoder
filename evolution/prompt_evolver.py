"""
PromptEvolver - Self-evolving system prompt management for EvoCoder.

Analyse task execution results, detect failure patterns, and propose
evolved system prompts that address recurring problems.  Each evolution
is versioned so the system can accept, reject, or roll back changes.

Integrates with:
  - EvolutionTracker  -- task history and failure statistics
  - ErrorMemory       -- known errors and attempted fixes
  - StrategyMemory    -- per-category strategy prompts
  - UserPreferences   -- style guide injection

Core API:
  analyze_and_evolve()  -- inspect recent history, propose a new prompt
  get_prompt()          -- return the current active prompt
  accept_evolution()    -- confirm the proposed evolution as the new baseline
  rollback()            -- revert to the previous prompt version
  get_evolution_history() -- full audit trail of all prompt versions
"""

import json
import time
import uuid
import copy
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("evocoder.evolution.prompt_evolver")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PromptVersion:
    """Immutable snapshot of a single prompt version."""

    version_id: str
    prompt_text: str
    created_at: str
    parent_version_id: Optional[str]
    trigger: str                     # e.g. "auto_evolve", "manual", "rollback"
    reason: str                      # human-readable explanation
    analysis: Dict[str, Any]         # raw analysis that produced this version
    accepted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "prompt_text": self.prompt_text,
            "created_at": self.created_at,
            "parent_version_id": self.parent_version_id,
            "trigger": self.trigger,
            "reason": self.reason,
            "analysis": self.analysis,
            "accepted": self.accepted,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptVersion":
        return cls(**data)


# ---------------------------------------------------------------------------
# Default system prompt
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = (
    "You are EvoCoder, an intelligent coding assistant.  "
    "Break tasks into clear steps.  Write clean, well-structured code.  "
    "Handle errors explicitly.  Prefer readability over cleverness.  "
    "If a task is ambiguous, ask for clarification before proceeding."
)


# ---------------------------------------------------------------------------
# PromptEvolver
# ---------------------------------------------------------------------------

class PromptEvolver:
    """
    Self-evolving prompt manager.

    Analyses execution history from EvolutionTracker, consults ErrorMemory
    and StrategyMemory for context, and produces evolved system prompts
    that address observed failure patterns.

    Usage::

        evolver = PromptEvolver(tracker, error_mem, strategy_mem, user_prefs)
        # After running tasks...
        result = evolver.analyze_and_evolve()
        if result["evolution_proposed"]:
            # review the proposal
            print(result["proposed_prompt"])
            evolver.accept_evolution()
        current = evolver.get_prompt()
    """

    def __init__(
        self,
        tracker: Any = None,
        error_memory: Any = None,
        strategy_memory: Any = None,
        user_prefs: Any = None,
        *,
        persist_dir: str = ".evocoder/evolution",
        base_prompt: str = DEFAULT_SYSTEM_PROMPT,
        min_tasks_for_evolution: int = 5,
        failure_rate_threshold: float = 0.3,
        error_rate_threshold: float = 0.2,
        max_prompt_tokens: int = 2000,
        max_versions: int = 50,
    ):
        # External dependencies (duck-typed, any object with matching methods)
        self.tracker = tracker
        self.error_memory = error_memory
        self.strategy_memory = strategy_memory
        self.user_prefs = user_prefs

        # Configuration
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.min_tasks_for_evolution = min_tasks_for_evolution
        self.failure_rate_threshold = failure_rate_threshold
        self.error_rate_threshold = error_rate_threshold
        self.max_prompt_tokens = max_prompt_tokens
        self.max_versions = max_versions

        # Prompt version chain
        self._versions: List[PromptVersion] = []
        self._active_version_id: Optional[str] = None

        # Pending (unaccepted) proposal
        self._pending: Optional[PromptVersion] = None

        # Load persisted state
        self._load()

        # Seed initial version if empty
        if not self._versions:
            initial = PromptVersion(
                version_id=uuid.uuid4().hex[:12],
                prompt_text=base_prompt,
                created_at=datetime.now().isoformat(),
                parent_version_id=None,
                trigger="initial",
                reason="System initialisation",
                analysis={},
                accepted=True,
            )
            self._versions.append(initial)
            self._active_version_id = initial.version_id
            self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _state_path(self) -> Path:
        return self.persist_dir / "prompt_versions.json"

    def _load(self) -> None:
        """Load version history from disk."""
        path = self._state_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._versions = [
                PromptVersion.from_dict(v) for v in data.get("versions", [])
            ]
            self._active_version_id = data.get("active_version_id")
            pending_raw = data.get("pending")
            if pending_raw:
                self._pending = PromptVersion.from_dict(pending_raw)
            logger.info("Loaded %d prompt versions from %s", len(self._versions), path)
        except (json.JSONDecodeError, IOError, TypeError) as exc:
            logger.warning("Failed to load prompt versions: %s", exc)

    def _save(self) -> None:
        """Persist version history to disk."""
        data = {
            "active_version_id": self._active_version_id,
            "versions": [v.to_dict() for v in self._versions[-self.max_versions:]],
            "pending": self._pending.to_dict() if self._pending else None,
            "updated_at": datetime.now().isoformat(),
        }
        try:
            self._state_path().write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save prompt versions: %s", exc)

    # ------------------------------------------------------------------
    # Public API: get_prompt
    # ------------------------------------------------------------------

    def get_prompt(self, include_style: bool = True) -> str:
        """Return the current active system prompt.

        Args:
            include_style: If True, append the user's style guide from
                           UserPreferences (if available).

        Returns:
            The active prompt text.  Falls back to pending proposal
            if no accepted version exists, then to DEFAULT_SYSTEM_PROMPT.
        """
        # Prefer accepted active version
        prompt = self._get_active_prompt_text()

        # Append style guide
        if include_style and self.user_prefs is not None:
            try:
                style = self.user_prefs.get_style_prompt()
                if style:
                    prompt = f"{prompt}\n\n[Style Guide]\n{style}"
            except Exception:
                pass  # user_prefs may not have this method

        return prompt

    def _get_active_prompt_text(self) -> str:
        """Get the raw prompt text of the active version."""
        for v in self._versions:
            if v.version_id == self._active_version_id:
                return v.prompt_text
        # Fallback: use most recent accepted
        for v in reversed(self._versions):
            if v.accepted:
                return v.prompt_text
        # Ultimate fallback
        return DEFAULT_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Public API: analyze_and_evolve
    # ------------------------------------------------------------------

    def analyze_and_evolve(
        self,
        *,
        force: bool = False,
        custom_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyse recent task history and propose an evolved prompt if needed.

        The analysis inspects:
        1. Overall failure rate from EvolutionTracker
        2. Error patterns from ErrorMemory (recurring error types)
        3. Strategy effectiveness from StrategyMemory
        4. Per-category hotspots (categories with high failure rates)

        If the evidence is strong enough (or ``force=True``), a new prompt
        version is proposed.  The proposal is NOT automatically accepted --
        call ``accept_evolution()`` to confirm.

        Args:
            force: Bypass thresholds and propose an evolution regardless.
            custom_context: Extra context to inject into the evolved prompt.

        Returns:
            Dict with keys:
              - evolution_proposed (bool)
              - analysis (dict): the raw analysis data
              - proposed_prompt (str | None): the new prompt text
              - changes (list[str]): summary of what changed
              - version_id (str | None): id of the proposed version
        """
        analysis = self._gather_analysis()
        should_evolve, reasons = self._should_evolve(analysis, force)

        result: Dict[str, Any] = {
            "evolution_proposed": False,
            "analysis": analysis,
            "proposed_prompt": None,
            "changes": [],
            "version_id": None,
        }

        if not should_evolve:
            result["reason"] = "No evolution needed at this time."
            if reasons:
                result["reason"] += "  " + "; ".join(reasons)
            logger.info("No evolution proposed: %s", result["reason"])
            return result

        # Build the evolved prompt
        current_prompt = self._get_active_prompt_text()
        evolved_prompt, changes = self._build_evolved_prompt(
            current_prompt, analysis, custom_context,
        )

        # Guard: if the evolved prompt is identical to current, skip
        if evolved_prompt.strip() == current_prompt.strip():
            result["reason"] = "Evolved prompt is identical to current prompt."
            logger.info("Evolution skipped: no actual changes.")
            return result

        # Create the proposed version
        parent_id = self._active_version_id
        new_version = PromptVersion(
            version_id=uuid.uuid4().hex[:12],
            prompt_text=evolved_prompt,
            created_at=datetime.now().isoformat(),
            parent_version_id=parent_id,
            trigger="auto_evolve",
            reason="; ".join(reasons) if reasons else "Periodic evolution",
            analysis=analysis,
            accepted=False,
            metadata={
                "changes": changes,
                "forced": force,
            },
        )

        self._pending = new_version
        self._save()

        result["evolution_proposed"] = True
        result["proposed_prompt"] = evolved_prompt
        result["changes"] = changes
        result["version_id"] = new_version.version_id

        logger.info(
            "Evolution proposed: version=%s, changes=%d",
            new_version.version_id, len(changes),
        )
        return result

    # ------------------------------------------------------------------
    # Public API: accept_evolution
    # ------------------------------------------------------------------

    def accept_evolution(
        self,
        version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Accept a pending prompt evolution, making it the active version.

        Args:
            version_id: The version to accept.  If None, accepts the
                        current pending proposal.

        Returns:
            Dict with keys:
              - accepted (bool)
              - version_id (str)
              - prompt_preview (str): first 200 chars of the new prompt

        Raises:
            ValueError: If no matching pending version exists.
        """
        target = self._pending

        if version_id is not None:
            # Allow accepting any unaccepted version in history
            for v in self._versions:
                if v.version_id == version_id and not v.accepted:
                    target = v
                    break
            else:
                # Also check pending
                if self._pending and self._pending.version_id == version_id:
                    target = self._pending
                else:
                    raise ValueError(
                        f"No unaccepted version found with id '{version_id}'"
                    )

        if target is None:
            raise ValueError("No pending evolution to accept.")

        # Mark as accepted
        target.accepted = True

        # Add to version chain if not already there
        if not any(v.version_id == target.version_id for v in self._versions):
            self._versions.append(target)

        self._active_version_id = target.version_id
        self._pending = None
        self._save()

        logger.info("Accepted evolution version %s", target.version_id)

        return {
            "accepted": True,
            "version_id": target.version_id,
            "prompt_preview": target.prompt_text[:200],
        }

    # ------------------------------------------------------------------
    # Public API: rollback
    # ------------------------------------------------------------------

    def rollback(
        self,
        version_id: Optional[str] = None,
        steps: int = 1,
    ) -> Dict[str, Any]:
        """
        Revert to a previous prompt version.

        Args:
            version_id: Specific version to roll back to.  If None,
                        rolls back ``steps`` versions from the current.
            steps: Number of versions to go back (ignored if version_id given).

        Returns:
            Dict with keys:
              - rolled_back (bool)
              - from_version (str): the version that was active
              - to_version (str): the version now active
              - prompt_preview (str): first 200 chars

        Raises:
            ValueError: If the target version cannot be found.
        """
        if version_id is not None:
            target = None
            for v in self._versions:
                if v.version_id == version_id:
                    target = v
                    break
            if target is None:
                raise ValueError(f"Version '{version_id}' not found.")
        else:
            # Walk backwards through accepted versions
            accepted = [v for v in self._versions if v.accepted]
            if len(accepted) < steps + 1:
                raise ValueError(
                    f"Not enough accepted versions to roll back {steps} step(s). "
                    f"Only {len(accepted)} available."
                )
            target = accepted[-(steps + 1)]

        old_version_id = self._active_version_id

        # Create a rollback "version" that copies the target's prompt
        rollback_version = PromptVersion(
            version_id=uuid.uuid4().hex[:12],
            prompt_text=target.prompt_text,
            created_at=datetime.now().isoformat(),
            parent_version_id=self._active_version_id,
            trigger="rollback",
            reason=f"Rollback to version {target.version_id}",
            analysis={"rollback_from": old_version_id, "rollback_to": target.version_id},
            accepted=True,
            metadata={"original_version_id": target.version_id},
        )

        self._versions.append(rollback_version)
        self._active_version_id = rollback_version.version_id
        self._pending = None
        self._save()

        logger.info(
            "Rolled back from %s to %s (via rollback version %s)",
            old_version_id, target.version_id, rollback_version.version_id,
        )

        return {
            "rolled_back": True,
            "from_version": old_version_id,
            "to_version": rollback_version.version_id,
            "prompt_preview": rollback_version.prompt_text[:200],
        }

    # ------------------------------------------------------------------
    # Public API: get_evolution_history
    # ------------------------------------------------------------------

    def get_evolution_history(
        self,
        *,
        include_analysis: bool = False,
        only_accepted: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Return the full audit trail of prompt versions.

        Args:
            include_analysis: If True, include the raw analysis dict in
                              each entry (can be verbose).
            only_accepted: If True, exclude rejected/unaccepted versions.

        Returns:
            List of version dicts ordered chronologically.
        """
        history = []
        for v in self._versions:
            if only_accepted and not v.accepted:
                continue
            entry = v.to_dict()
            entry["is_active"] = (v.version_id == self._active_version_id)
            if not include_analysis:
                entry.pop("analysis", None)
            history.append(entry)
        return history

    # ------------------------------------------------------------------
    # Public API: set_prompt (manual override)
    # ------------------------------------------------------------------

    def set_prompt(
        self,
        prompt_text: str,
        reason: str = "Manual override",
    ) -> Dict[str, Any]:
        """Manually set a new prompt, bypassing the evolution analysis.

        Args:
            prompt_text: The new system prompt text.
            reason: Why this change was made.

        Returns:
            Dict with accepted status and version info.
        """
        version = PromptVersion(
            version_id=uuid.uuid4().hex[:12],
            prompt_text=prompt_text,
            created_at=datetime.now().isoformat(),
            parent_version_id=self._active_version_id,
            trigger="manual",
            reason=reason,
            analysis={},
            accepted=True,
        )
        self._versions.append(version)
        self._active_version_id = version.version_id
        self._pending = None
        self._save()

        logger.info("Manual prompt override: version=%s", version.version_id)

        return {
            "accepted": True,
            "version_id": version.version_id,
            "prompt_preview": prompt_text[:200],
        }

    # ------------------------------------------------------------------
    # Public API: get_pending
    # ------------------------------------------------------------------

    def get_pending(self) -> Optional[Dict[str, Any]]:
        """Return the pending (unaccepted) proposal, or None."""
        if self._pending is None:
            return None
        return self._pending.to_dict()

    # ------------------------------------------------------------------
    # Public API: reject_pending
    # ------------------------------------------------------------------

    def reject_pending(self) -> bool:
        """Reject and discard the current pending proposal.

        Returns:
            True if a proposal was rejected, False if none existed.
        """
        if self._pending is None:
            return False
        version_id = self._pending.version_id
        self._pending = None
        self._save()
        logger.info("Rejected pending evolution %s", version_id)
        return True

    # ------------------------------------------------------------------
    # Public API: summary
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """High-level summary of the prompt evolver state."""
        accepted = [v for v in self._versions if v.accepted]
        return {
            "total_versions": len(self._versions),
            "accepted_versions": len(accepted),
            "active_version_id": self._active_version_id,
            "active_prompt_preview": self._get_active_prompt_text()[:200],
            "has_pending": self._pending is not None,
            "pending_preview": self._pending.prompt_text[:200] if self._pending else None,
            "latest_trigger": self._versions[-1].trigger if self._versions else None,
        }

    # ------------------------------------------------------------------
    # Internal: analysis gathering
    # ------------------------------------------------------------------

    def _gather_analysis(self) -> Dict[str, Any]:
        """Collect signals from all connected subsystems."""
        analysis: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "task_stats": {},
            "error_patterns": {},
            "strategy_effectiveness": {},
            "hotspot_categories": [],
        }

        # -- Task stats from EvolutionTracker --
        if self.tracker is not None:
            try:
                if hasattr(self.tracker, "summary"):
                    analysis["task_stats"] = self.tracker.summary()
                elif hasattr(self.tracker, "get_category_stats"):
                    analysis["task_stats"] = {
                        k: v.to_dict() if hasattr(v, "to_dict") else v
                        for k, v in self.tracker.get_category_stats().items()
                    }
            except Exception as exc:
                logger.debug("Failed to gather tracker stats: %s", exc)

        # -- Error patterns from ErrorMemory --
        if self.error_memory is not None:
            try:
                if hasattr(self.error_memory, "get_pitfall_summary"):
                    analysis["error_patterns"] = self.error_memory.get_pitfall_summary()
            except Exception as exc:
                logger.debug("Failed to gather error patterns: %s", exc)

        # -- Strategy effectiveness from StrategyMemory --
        if self.strategy_memory is not None:
            try:
                if hasattr(self.strategy_memory, "get_stats"):
                    analysis["strategy_effectiveness"] = self.strategy_memory.get_stats()
            except Exception as exc:
                logger.debug("Failed to gather strategy stats: %s", exc)

        # -- Identify hotspot categories --
        analysis["hotspot_categories"] = self._find_hotspots(analysis)

        return analysis

    def _find_hotspots(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify task categories with unusually high failure rates."""
        hotspots: List[Dict[str, Any]] = []

        # From task_stats (tracker summary)
        task_stats = analysis.get("task_stats", {})
        categories = task_stats.get("categories", {})

        for cat_name, cat_data in categories.items():
            if isinstance(cat_data, dict):
                success_rate = cat_data.get("success_rate", 1.0)
                total = cat_data.get("total_tasks", 0)
                if total >= self.min_tasks_for_evolution and success_rate < (1 - self.failure_rate_threshold):
                    hotspots.append({
                        "category": cat_name,
                        "success_rate": success_rate,
                        "total_tasks": total,
                        "failure_rate": round(1 - success_rate, 3),
                    })

        # From error patterns
        error_patterns = analysis.get("error_patterns", {})
        common_type = error_patterns.get("most_common_type")
        if common_type:
            total_errors = error_patterns.get("total_errors", 0)
            if total_errors >= 3:
                hotspots.append({
                    "category": f"error_type:{common_type}",
                    "total_errors": total_errors,
                    "error_breakdown": error_patterns.get("error_breakdown", {}),
                })

        return hotspots

    # ------------------------------------------------------------------
    # Internal: evolution decision
    # ------------------------------------------------------------------

    def _should_evolve(
        self,
        analysis: Dict[str, Any],
        force: bool,
    ) -> Tuple[bool, List[str]]:
        """Decide whether the evidence warrants an evolution.

        Returns:
            (should_evolve, list_of_reasons)
        """
        reasons: List[str] = []

        if force:
            reasons.append("Forced evolution requested")
            return True, reasons

        # Check task stats
        task_stats = analysis.get("task_stats", {})
        total_tasks = task_stats.get("total_tasks", 0)
        success_rate = task_stats.get("success_rate", 1.0)
        should_evolve_flag = task_stats.get("should_evolve", False)

        if total_tasks < self.min_tasks_for_evolution:
            reasons.append(
                f"Not enough tasks yet ({total_tasks} < {self.min_tasks_for_evolution})"
            )
            return False, reasons

        if should_evolve_flag:
            reasons.append("EvolutionTracker reports should_evolve=True")

        failure_rate = 1.0 - success_rate
        if failure_rate > self.failure_rate_threshold:
            reasons.append(
                f"High failure rate: {failure_rate:.1%} > {self.failure_rate_threshold:.1%}"
            )

        # Check error patterns
        error_patterns = analysis.get("error_patterns", {})
        total_errors = error_patterns.get("total_errors", 0)
        if total_errors > 0 and total_tasks > 0:
            error_rate = total_errors / total_tasks
            if error_rate > self.error_rate_threshold:
                reasons.append(
                    f"High error rate: {error_rate:.2f} errors/task > {self.error_rate_threshold}"
                )

        # Check hotspot categories
        hotspots = analysis.get("hotspot_categories", [])
        if len(hotspots) >= 2:
            reasons.append(f"{len(hotspots)} hotspot categories detected")

        # Check strategy effectiveness for very bad strategies
        strategy_stats = analysis.get("strategy_effectiveness", {})
        weak_strategies = []
        for cat, stats in strategy_stats.items():
            if isinstance(stats, dict):
                sr = stats.get("success_rate", 1.0)
                total = stats.get("total_tasks", 0)
                if total >= 3 and sr < 0.4:
                    weak_strategies.append(f"{cat}({sr:.0%})")
        if weak_strategies:
            reasons.append(f"Weak strategies: {', '.join(weak_strategies)}")

        # Need at least one strong signal
        strong_signals = [r for r in reasons if r not in (
            f"Not enough tasks yet ({total_tasks} < {self.min_tasks_for_evolution})",
        )]
        if not strong_signals:
            return False, ["No strong evolution signals detected"]

        return True, reasons

    # ------------------------------------------------------------------
    # Internal: prompt construction
    # ------------------------------------------------------------------

    def _build_evolved_prompt(
        self,
        current_prompt: str,
        analysis: Dict[str, Any],
        custom_context: Optional[str],
    ) -> Tuple[str, List[str]]:
        """Construct an evolved prompt addressing detected issues.

        Returns:
            (evolved_prompt, list_of_change_descriptions)
        """
        changes: List[str] = []
        sections: List[str] = []

        # -- Start with the base prompt, trimmed --
        base = current_prompt.rstrip()
        sections.append(base)

        # -- Error avoidance section --
        error_section = self._build_error_avoidance_section(analysis)
        if error_section:
            sections.append(error_section)
            changes.append("Added error-avoidance rules from error memory")

        # -- Strategy refinements --
        strategy_section = self._build_strategy_section(analysis)
        if strategy_section:
            sections.append(strategy_section)
            changes.append("Added strategy refinements from weak categories")

        # -- Category-specific guidance --
        category_section = self._build_category_guidance(analysis)
        if category_section:
            sections.append(category_section)
            changes.append("Added category-specific guidance for hotspots")

        # -- Custom context --
        if custom_context:
            sections.append(f"[Additional Context]\n{custom_context}")
            changes.append("Added custom context")

        evolved_prompt = "\n\n".join(sections)

        # Truncate if too long (rough estimate: 1 token ~ 4 chars)
        max_chars = self.max_prompt_tokens * 4
        if len(evolved_prompt) > max_chars:
            evolved_prompt = evolved_prompt[:max_chars] + "\n...[truncated]"
            changes.append("Truncated prompt to fit token budget")

        return evolved_prompt, changes

    def _build_error_avoidance_section(self, analysis: Dict[str, Any]) -> str:
        """Build a section addressing known error patterns."""
        error_patterns = analysis.get("error_patterns", {})
        tips = error_patterns.get("tips", [])
        recent_pitfalls = error_patterns.get("recent_pitfalls", [])

        if not tips and not recent_pitfalls:
            return ""

        lines = ["[Error Avoidance Rules]"]

        if tips:
            for tip in tips[:5]:
                lines.append(f"- {tip}")

        if recent_pitfalls:
            lines.append("")
            lines.append("Recent failure patterns to avoid:")
            for pitfall in recent_pitfalls[:3]:
                lines.append(f"- {pitfall[:100]}")

        return "\n".join(lines)

    def _build_strategy_section(self, analysis: Dict[str, Any]) -> str:
        """Build a section with refined strategy instructions."""
        strategy_stats = analysis.get("strategy_effectiveness", {})
        if not strategy_stats:
            return ""

        weak = []
        for cat, stats in strategy_stats.items():
            if isinstance(stats, dict):
                sr = stats.get("success_rate", 1.0)
                total = stats.get("total_tasks", 0)
                if total >= 3 and sr < 0.5:
                    weak.append((cat, sr, total))

        if not weak:
            return ""

        lines = ["[Strategy Refinements]"]
        lines.append("Pay extra attention to these task categories:")

        for cat, sr, total in sorted(weak, key=lambda x: x[1]):
            lines.append(f"- {cat}: success rate {sr:.0%} over {total} tasks")
            # Add specific guidance per category
            guidance = self._category_specific_advice(cat)
            if guidance:
                lines.append(f"  Guidance: {guidance}")

        return "\n".join(lines)

    def _build_category_guidance(self, analysis: Dict[str, Any]) -> str:
        """Build guidance for hotspot categories."""
        hotspots = analysis.get("hotspot_categories", [])
        if not hotspots:
            return ""

        lines = ["[Category-Specific Guidance]"]

        for spot in hotspots:
            cat = spot.get("category", "")
            fr = spot.get("failure_rate", 0)

            if cat.startswith("error_type:"):
                error_type = cat.split(":", 1)[1]
                lines.append(f"- Recurring error type: {error_type}")
                lines.append(f"  Take extra precautions when handling {error_type}-prone operations.")
            else:
                lines.append(f"- Category '{cat}' has {fr:.0%} failure rate")
                advice = self._category_specific_advice(cat)
                if advice:
                    lines.append(f"  {advice}")

        return "\n".join(lines)

    @staticmethod
    def _category_specific_advice(category: str) -> str:
        """Return targeted advice for a known task category."""
        advice_map = {
            "debug": (
                "Always reproduce the bug first.  Check recent changes.  "
                "Fix root cause, not symptoms.  Write a regression test."
            ),
            "code": (
                "Plan before coding.  Handle edge cases explicitly.  "
                "Write tests alongside implementation."
            ),
            "refactor": (
                "Ensure tests pass before starting.  Make one change at a time.  "
                "Verify after each change."
            ),
            "file": (
                "Validate paths before reading/writing.  Handle encoding explicitly.  "
                "Use context managers for file I/O."
            ),
            "git": (
                "Check status before committing.  Keep commits atomic.  "
                "Write clear commit messages."
            ),
            "search": (
                "Start broad, then narrow.  Verify findings from multiple sources."
            ),
        }
        return advice_map.get(category, "")

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._versions)

    def __repr__(self) -> str:
        return (
            f"PromptEvolver(versions={len(self._versions)}, "
            f"active={self._active_version_id}, "
            f"pending={self._pending is not None})"
        )


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    import shutil

    tmpdir = tempfile.mkdtemp()
    try:
        evolver = PromptEvolver(persist_dir=tmpdir)

        print("Initial prompt:")
        print(evolver.get_prompt())
        print(f"\nSummary: {json.dumps(evolver.summary(), indent=2)}")

        # Simulate analysis (no tracker attached, so it will be sparse)
        result = evolver.analyze_and_evolve(force=True)
        print(f"\nEvolution result: proposed={result['evolution_proposed']}")

        if result["evolution_proposed"]:
            print(f"Changes: {result['changes']}")
            accept_result = evolver.accept_evolution()
            print(f"Accepted: {accept_result}")

        # Manual override
        evolver.set_prompt("You are a specialized Python debugging assistant.")
        print(f"\nAfter manual override: {evolver.summary()}")

        # Rollback
        rb = evolver.rollback(steps=1)
        print(f"\nRollback: {rb}")

        # History
        history = evolver.get_evolution_history()
        print(f"\nEvolution history ({len(history)} versions):")
        for entry in history:
            print(f"  [{entry['version_id']}] {entry['trigger']} - {entry['reason'][:60]}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print("\nDone. Cleaned up temp directory.")
