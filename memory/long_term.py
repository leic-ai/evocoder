"""
LongTermMemory - Persistent user profile, session history, and learned knowledge.

Manages three JSON files:
  - user.json      -- user profile (name, tags, visit_count, first_seen, last_seen)
  - history.json   -- session log (last 20 sessions with timestamps and summaries)
  - learned.json   -- accumulated knowledge snippets (facts, preferences, corrections)

Designed to work alongside MemoryStore: MemoryStore handles conversational
memory and experiences; LongTermMemory handles the "who is the user" and
"what have we learned across sessions" layer.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("evocoder.memory.long_term")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SESSION_HISTORY = 20
"""Maximum number of sessions to retain in history.json."""


# ---------------------------------------------------------------------------
# LongTermMemory
# ---------------------------------------------------------------------------

class LongTermMemory:
    """Persistent long-term memory across EvoCoder sessions.

    Manages three JSON files in a single data directory:

    **user.json** -- User profile::

        {
            "name": "",
            "tags": [],
            "visit_count": 0,
            "first_seen": "2026-01-15T10:30:00",
            "last_seen":  "2026-06-08T14:22:00"
        }

    **history.json** -- Session log (ring buffer, last 20)::

        {
            "sessions": [
                {
                    "session_id": "20260608_142200",
                    "started_at": "2026-06-08T14:22:00",
                    "ended_at":   "2026-06-08T15:01:00",
                    "summary":    "Implemented file upload handler",
                    "tags":       ["file", "async"]
                },
                ...
            ]
        }

    **learned.json** -- Accumulated knowledge::

        {
            "facts": [
                {
                    "id":         "f001",
                    "content":    "User prefers async/await over threading",
                    "category":   "preference",
                    "added_at":   "2026-06-08T14:22:00",
                    "source":     "explicit"
                },
                ...
            ]
        }

    Usage::

        mem = LongTermMemory(data_dir=".evocoder/memory")

        # On session start
        mem.update_user(name="Alice", tags=["python", "ml"])
        mem.start_session()

        # During session
        mem.add_fact("User prefers dark mode", category="preference")

        # On session end
        mem.end_session(summary="Built ML pipeline", tags=["ml", "pipeline"])

        # Build system prompt context
        ctx = mem.get_context()
        greeting = mem.get_greeting()
    """

    def __init__(self, data_dir: str = ".evocoder/memory"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._user_path = self.data_dir / "user.json"
        self._history_path = self.data_dir / "history.json"
        self._learned_path = self.data_dir / "learned.json"

        self._user: Dict[str, Any] = self._load_json(self._user_path, {
            "name": "",
            "tags": [],
            "visit_count": 0,
            "first_seen": None,
            "last_seen": None,
        })
        self._history: Dict[str, Any] = self._load_json(self._history_path, {
            "sessions": [],
        })
        self._learned: Dict[str, Any] = self._load_json(self._learned_path, {
            "facts": [],
        })

        self._current_session_id: Optional[str] = None

        logger.info(
            "LongTermMemory loaded: user='%s', visits=%d, sessions=%d, facts=%d",
            self._user.get("name", ""),
            self._user.get("visit_count", 0),
            len(self._history.get("sessions", [])),
            len(self._learned.get("facts", [])),
        )

    # ===================================================================
    # User profile
    # ===================================================================

    def update_user(
        self,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update user profile and increment visit count.

        Args:
            name: User's display name.  Pass None to leave unchanged.
                  Pass empty string to clear.
            tags: List of tags/interests.  Pass None to leave unchanged.
                  Pass empty list to clear all tags.

        Returns:
            The updated user profile dict.
        """
        now = datetime.now().isoformat()

        # First visit ever
        if self._user.get("first_seen") is None:
            self._user["first_seen"] = now

        # Update fields
        if name is not None:
            self._user["name"] = name

        if tags is not None:
            existing = set(self._user.get("tags", []))
            existing.update(tags)
            self._user["tags"] = sorted(existing)

        self._user["visit_count"] = self._user.get("visit_count", 0) + 1
        self._user["last_seen"] = now

        self._save_json(self._user_path, self._user)
        logger.debug("User updated: name='%s', visit_count=%d", self._user["name"], self._user["visit_count"])
        return dict(self._user)

    def get_user(self) -> Dict[str, Any]:
        """Return a copy of the current user profile."""
        return dict(self._user)

    # ===================================================================
    # Session history
    # ===================================================================

    def start_session(self) -> str:
        """Mark the beginning of a new session.

        Returns:
            The generated session ID (timestamp-based).
        """
        now = datetime.now()
        self._current_session_id = now.strftime("%Y%m%d_%H%M%S")
        logger.info("Session started: %s", self._current_session_id)
        return self._current_session_id

    def add_session(
        self,
        summary: str = "",
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a completed session in history.

        Keeps only the last MAX_SESSION_HISTORY sessions (ring buffer).

        Args:
            summary: Brief description of what was accomplished.
            tags: Keywords describing the session content.
            session_id: Override the session ID (defaults to current or generated).

        Returns:
            The session entry dict that was stored.
        """
        now = datetime.now().isoformat()
        sid = session_id or self._current_session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        entry: Dict[str, Any] = {
            "session_id": sid,
            "started_at": self._user.get("last_seen", now),
            "ended_at": now,
            "summary": summary,
            "tags": tags or [],
        }

        sessions: List[Dict[str, Any]] = self._history.get("sessions", [])
        sessions.append(entry)

        # Ring buffer: keep only the last MAX_SESSION_HISTORY
        if len(sessions) > MAX_SESSION_HISTORY:
            sessions = sessions[-MAX_SESSION_HISTORY:]
            self._history["sessions"] = sessions

        self._save_json(self._history_path, self._history)
        self._current_session_id = None
        logger.debug("Session recorded: %s (%s)", sid, summary[:60] if summary else "(no summary)")
        return entry

    def get_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent session entries, newest first.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of session dicts.
        """
        sessions: List[Dict[str, Any]] = self._history.get("sessions", [])
        return list(reversed(sessions[-limit:]))

    def get_session_count(self) -> int:
        """Total number of recorded sessions."""
        return len(self._history.get("sessions", []))

    # ===================================================================
    # Learned knowledge
    # ===================================================================

    def add_fact(
        self,
        content: str,
        category: str = "general",
        source: str = "inferred",
    ) -> Dict[str, Any]:
        """Store a learned fact or preference.

        Args:
            content: The knowledge snippet (e.g. "User prefers Python 3.12").
            category: Classification (preference, correction, fact, habit, etc.).
            source: How this was learned (explicit, inferred, correction).

        Returns:
            The fact entry dict.
        """
        fact_id = f"f{len(self._learned.get('facts', [])) + 1:04d}"
        entry: Dict[str, Any] = {
            "id": fact_id,
            "content": content,
            "category": category,
            "added_at": datetime.now().isoformat(),
            "source": source,
        }

        self._learned.setdefault("facts", []).append(entry)
        self._save_json(self._learned_path, self._learned)
        logger.debug("Fact added [%s]: %s", fact_id, content[:80])
        return entry

    def get_facts(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve learned facts, optionally filtered by category.

        Args:
            category: Filter to this category, or None for all.
            limit: Maximum entries to return.

        Returns:
            List of fact dicts, newest first.
        """
        facts: List[Dict[str, Any]] = self._learned.get("facts", [])
        if category:
            facts = [f for f in facts if f.get("category") == category]
        return list(reversed(facts[-limit:]))

    def remove_fact(self, fact_id: str) -> bool:
        """Remove a fact by its ID.

        Returns:
            True if the fact was found and removed, False otherwise.
        """
        facts: List[Dict[str, Any]] = self._learned.get("facts", [])
        for i, f in enumerate(facts):
            if f.get("id") == fact_id:
                facts.pop(i)
                self._save_json(self._learned_path, self._learned)
                logger.debug("Fact removed: %s", fact_id)
                return True
        return False

    # ===================================================================
    # Greeting with Easter egg
    # ===================================================================

    def get_greeting(self) -> str:
        """Generate a personalised greeting for the user.

        Behavior:
          - First visit: welcome message.
          - Returning user: "Welcome back, {name}!" with visit count.
          - Easter egg: if the tag "丑鲸鱼" appears in the user's tags,
            returns a special message instead.

        Returns:
            Greeting string.
        """
        tags = self._user.get("tags", [])
        name = self._user.get("name", "")
        visit_count = self._user.get("visit_count", 0)

        # --- Easter egg ---
        if "ugly-whale" in str(tags):
            return "✨ The Ugly Whale has arrived! What shall we conquer today? ✨"

        # --- First visit ---
        if visit_count <= 1:
            if name:
                return f"Hi {name}! Welcome to EvoCoder. How can I help?"
            return "Hi! Welcome to EvoCoder. How can I help?"

        # --- Returning user ---
        if name:
            return f"Welcome back, {name}! This is your {visit_count}th visit. What can I do for you?"
        return f"Welcome back! This is your {visit_count}th visit. What can I do for you?"

    # ===================================================================
    # System prompt context injection
    # ===================================================================

    def get_context(self) -> str:
        """Build a context string to inject into the system prompt.

        Includes:
          - User profile (name, tags, visit count)
          - Recent session summaries (last 3)
          - Relevant learned facts (preferences and corrections)

        Returns:
            A multi-line string suitable for appending to the system prompt.
            Returns empty string if no meaningful context exists.
        """
        sections: List[str] = []

        # --- User profile ---
        name = self._user.get("name", "")
        tags = self._user.get("tags", [])
        visit_count = self._user.get("visit_count", 0)

        if name or tags or visit_count > 1:
            profile_lines = ["[User Profile]"]
            if name:
                profile_lines.append(f"  Name: {name}")
            if tags:
                profile_lines.append(f"  Interests: {', '.join(tags)}")
            if visit_count > 1:
                profile_lines.append(f"  Visit #{visit_count}")
            sections.append("\n".join(profile_lines))

        # --- Recent sessions ---
        recent_sessions = self.get_sessions(limit=3)
        if recent_sessions:
            session_lines = ["[Recent Sessions]"]
            for s in recent_sessions:
                sid = s.get("session_id", "?")
                summary = s.get("summary", "(no summary)")
                session_lines.append(f"  - [{sid}] {summary}")
            sections.append("\n".join(session_lines))

        # --- Learned facts: preferences and corrections ---
        preferences = self.get_facts(category="preference", limit=5)
        corrections = self.get_facts(category="correction", limit=5)
        if preferences or corrections:
            fact_lines = ["[Learned Knowledge]"]
            for f in preferences:
                fact_lines.append(f"  Preference: {f['content']}")
            for f in corrections:
                fact_lines.append(f"  Correction: {f['content']}")
            sections.append("\n".join(fact_lines))

        if not sections:
            return ""

        return "\n\n".join(sections) + "\n"

    # ===================================================================
    # Persistence helpers
    # ===================================================================

    @staticmethod
    def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
        """Load a JSON file, returning *default* if missing or corrupt."""
        if not path.exists():
            return dict(default)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            logger.warning("Non-dict JSON in %s, using defaults", path)
            return dict(default)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load %s: %s", path, exc)
            return dict(default)

    @staticmethod
    def _save_json(path: Path, data: Dict[str, Any]) -> None:
        """Atomically write a dict as formatted JSON."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save %s: %s", path, exc)

    # ===================================================================
    # Diagnostics
    # ===================================================================

    def summary(self) -> Dict[str, Any]:
        """High-level summary of long-term memory state."""
        return {
            "user": {
                "name": self._user.get("name", ""),
                "tags": self._user.get("tags", []),
                "visit_count": self._user.get("visit_count", 0),
                "first_seen": self._user.get("first_seen"),
                "last_seen": self._user.get("last_seen"),
            },
            "sessions": {
                "total": len(self._history.get("sessions", [])),
                "max_retained": MAX_SESSION_HISTORY,
            },
            "learned": {
                "total_facts": len(self._learned.get("facts", [])),
                "categories": self._fact_category_counts(),
            },
        }

    def _fact_category_counts(self) -> Dict[str, int]:
        """Count facts by category."""
        counts: Dict[str, int] = {}
        for f in self._learned.get("facts", []):
            cat = f.get("category", "unknown")
            counts[cat] = counts.get(cat, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def __repr__(self) -> str:
        return (
            f"LongTermMemory(user='{self._user.get('name', '')}', "
            f"visits={self._user.get('visit_count', 0)}, "
            f"sessions={len(self._history.get('sessions', []))}, "
            f"facts={len(self._learned.get('facts', []))})"
        )


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import tempfile
    import shutil

    # Ensure UTF-8 output on Windows terminals
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

    tmpdir = tempfile.mkdtemp(prefix="evocoder_lt_")
    try:
        mem = LongTermMemory(data_dir=tmpdir)

        # --- First visit ---
        print("=== First Visit ===")
        mem.update_user(name="Alice", tags=["python", "ml"])
        mem.start_session()
        print(f"Greeting: {mem.get_greeting()}")
        print(f"User: {mem.get_user()}")

        # --- Add some facts ---
        mem.add_fact("Prefers async/await over threading", category="preference", source="explicit")
        mem.add_fact("Uses Python 3.12", category="preference", source="inferred")
        mem.add_fact("Should use pathlib, not os.path", category="correction", source="explicit")

        # --- End session ---
        mem.add_session(summary="Built ML data pipeline", tags=["ml", "pipeline"])

        # --- Second visit ---
        print("\n=== Second Visit ===")
        mem.update_user(tags=["deep-learning"])
        mem.start_session()
        print(f"Greeting: {mem.get_greeting()}")

        # --- Easter egg visit ---
        print("\n=== Easter Egg Visit ===")
        mem.update_user(tags=["丑鲸鱼"])
        print(f"Greeting: {mem.get_greeting()}")

        # --- System prompt context ---
        print("\n=== System Prompt Context ===")
        print(mem.get_context())

        # --- Summary ---
        print("=== Summary ===")
        import json as _json
        print(_json.dumps(mem.summary(), ensure_ascii=False, indent=2))
        print(f"\nRepr: {mem}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print("\nDone. Cleaned up temp directory.")
