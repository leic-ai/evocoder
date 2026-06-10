"""
MemoryStore - Unified memory system for EvoCoder.

Three memory tiers:
  - Short-term conversation buffer (ring buffer, in-memory only)
  - Working memory context (structured key-value snapshot for current session)
  - Long-term experience store (persistent JSONL file + optional vector search)

Also manages prompt version snapshots for the PromptEvolver.

Vector search uses ChromaDB when available, falling back to keyword-based
matching when chromadb is not installed or the collection is empty.
"""

import re
import json
import time
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

logger = logging.getLogger("evocoder.memory.store")

# ---------------------------------------------------------------------------
# ChromaDB availability check (optional dependency)
# ---------------------------------------------------------------------------

_chromadb_available = False
_chroma_client = None

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    _chromadb_available = True
except ImportError:
    chromadb = None  # type: ignore[assignment]
    logger.info("chromadb not installed; vector search disabled, keyword fallback active")


# ---------------------------------------------------------------------------
# Experience dataclass-like dict schema
# ---------------------------------------------------------------------------

_EXPERIENCE_SCHEMA_HINT = """
Experience entry keys:
  id          -- unique hex id
  timestamp   -- ISO-8601 string
  category    -- task category (code, debug, refactor, file, git, search, general)
  task        -- task description (text)
  outcome     -- "success" | "failure" | "partial"
  solution    -- what was done / the working solution
  errors      -- list of error strings encountered
  duration    -- elapsed seconds (float or None)
  tags        -- list of short keyword strings
  metadata    -- arbitrary extra info dict
"""


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

class MemoryStore:
    """Unified three-tier memory for EvoCoder.

    Usage::

        store = MemoryStore(data_dir=".evocoder/memory")

        # Short-term: conversation buffer
        store.add_conversation("user", "Write a fibonacci function")
        store.add_conversation("assistant", "```python\\ndef fib...")
        recent = store.get_recent_conversation(n=6)

        # Working memory: session-scoped context
        store.set_working("current_task", "Fix login bug")
        store.set_working("error_context", "KeyError: 'user_id'")
        ctx = store.get_working_snapshot()

        # Long-term: experience
        store.record_experience(
            task="Fix login crash",
            category="debug",
            outcome="success",
            solution="Added .get() with default for user_id key",
            errors=["KeyError: 'user_id'"],
            tags=["dict", "key-error"],
        )
        similar = store.get_similar_experiences("KeyError when accessing config", top_k=3)

        # Prompt versions
        store.save_prompt_version("v1", "You are EvoCoder...", trigger="initial")
        prompts = store.list_prompt_versions()

    All long-term data persists across restarts via JSONL (experiences) and
    JSON (prompt versions, working memory).  ChromaDB vector search is used
    automatically when available.
    """

    def __init__(
        self,
        data_dir: str = ".evocoder/memory",
        conversation_limit: int = 200,
        long_term_path: Optional[str] = None,
        vector_collection: str = "evocoder_experiences",
        enable_vectors: bool = True,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # ---- Short-term: conversation ring buffer ----
        self._conversation_limit = conversation_limit
        self._conversation: deque = deque(maxlen=conversation_limit)

        # ---- Working memory: session context ----
        self._working: Dict[str, Any] = {}
        self._working_path = self.data_dir / "working_memory.json"
        self._load_working()

        # ---- Long-term: experiences (JSONL) ----
        self._long_term_path = Path(long_term_path) if long_term_path else self.data_dir / "experiences.jsonl"
        self._experiences: List[Dict[str, Any]] = []
        self._load_experiences()

        # ---- Prompt versions ----
        self._prompts_path = self.data_dir / "prompt_versions.json"
        self._prompt_versions: List[Dict[str, Any]] = []
        self._load_prompt_versions()

        # ---- Vector search (ChromaDB) ----
        self._vector_enabled = False
        self._chroma_collection = None
        if enable_vectors and _chromadb_available:
            self._init_vector_store(vector_collection)

        logger.info(
            "MemoryStore initialized: data_dir=%s, conversations=%d, experiences=%d, vectors=%s",
            self.data_dir, len(self._conversation), len(self._experiences),
            "ON" if self._vector_enabled else "OFF",
        )

    # ===================================================================
    # Short-term conversation buffer
    # ===================================================================

    def add_conversation(self, role: str, content: str) -> None:
        """Append a message to the conversation buffer.

        Args:
            role: "user", "assistant", or "system".
            content: The message text.
        """
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self._conversation.append(entry)

    def get_recent_conversation(self, n: int = 20) -> List[Dict[str, str]]:
        """Return the last *n* conversation messages.

        Args:
            n: Maximum number of messages to return.

        Returns:
            List of message dicts with role/content keys (no timestamp).
        """
        messages = list(self._conversation)[-n:]
        return [{"role": m["role"], "content": m["content"]} for m in messages]

    def clear_conversation(self) -> int:
        """Wipe the conversation buffer.  Returns count removed."""
        count = len(self._conversation)
        self._conversation.clear()
        return count

    @property
    def conversation_length(self) -> int:
        """Number of messages currently in the conversation buffer."""
        return len(self._conversation)

    def compress_context(
        self,
        messages: List[Dict[str, str]],
        target_count: int = 30,
        brain: Any = None,
    ) -> List[Dict[str, str]]:
        """Intelligently compress conversation history to fit within target count.

        Strategy:
          1. If messages already fit, return as-is.
          2. Split into old (to compress) and recent (to keep).
          3. If a Brain (LLM) is available, summarize old messages.
          4. Otherwise, keep first message + recent N messages.

        Args:
            messages: Full conversation history (role/content dicts).
            target_count: Target number of messages after compression.
            brain: Optional Brain instance for LLM-powered summarization.

        Returns:
            Compressed message list (system summary + recent messages).
        """
        if len(messages) <= target_count:
            return messages

        # Keep the most recent messages intact
        recent = messages[-target_count:]
        old_messages = messages[:-target_count]

        # Build a summary of old messages
        summary_parts = []
        for msg in old_messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")[:200]
            summary_parts.append(f"[{role}] {content}")

        summary_text = "\n".join(summary_parts)

        # Try LLM-powered summarization if brain is available
        if brain is not None:
            try:
                resp = brain.think([{
                    "role": "user",
                    "content": (
                        "Compress this conversation history into a concise summary. "
                        "Preserve: key decisions, tool results, error messages, "
                        "file paths mentioned, and any important context. "
                        "Remove: greetings, filler, redundant information.\n\n"
                        f"Conversation:\n{summary_text}"
                    ),
                }])
                summary_text = resp.content if hasattr(resp, 'content') else str(resp)
            except Exception:
                pass  # Summarization failed, use truncated original

        # Truncate summary if still too long
        max_summary_chars = 2000
        if len(summary_text) > max_summary_chars:
            summary_text = summary_text[:max_summary_chars] + "\n...[truncated]"

        # Return: summary as system message + recent messages
        return [
            {"role": "system", "content": f"[Conversation History Summary]\n{summary_text}"}
        ] + recent

    # ===================================================================
    # Working memory (session-scoped key-value context)
    # ===================================================================

    def set_working(self, key: str, value: Any) -> None:
        """Set a working-memory slot.

        Args:
            key: Context key (e.g. "current_task", "error_context").
            value: Any JSON-serialisable value.
        """
        self._working[key] = value
        self._save_working()

    def get_working(self, key: str, default: Any = None) -> Any:
        """Read a working-memory slot."""
        return self._working.get(key, default)

    def delete_working(self, key: str) -> bool:
        """Delete a working-memory slot.  Returns True if it existed."""
        if key in self._working:
            del self._working[key]
            self._save_working()
            return True
        return False

    def get_working_snapshot(self) -> Dict[str, Any]:
        """Return a copy of the entire working memory dict."""
        return dict(self._working)

    def clear_working(self) -> None:
        """Wipe all working memory."""
        self._working.clear()
        self._save_working()

    # ===================================================================
    # Long-term experience store
    # ===================================================================

    def record_experience(
        self,
        task: str,
        category: str,
        outcome: str,
        solution: str = "",
        errors: Optional[List[str]] = None,
        duration: Optional[float] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a new experience entry (persisted to JSONL + optional vector).

        Args:
            task: What was being done.
            category: Task category (code, debug, refactor, file, git, search, general).
            outcome: "success", "failure", or "partial".
            solution: Description of what worked (or was attempted).
            errors: Error messages encountered during this task.
            duration: Elapsed time in seconds.
            tags: Short keyword tags for retrieval.
            metadata: Arbitrary extra data.

        Returns:
            The full experience entry dict.
        """
        exp_id = hashlib.sha256(
            f"{task}{time.time()}{category}".encode()
        ).hexdigest()[:16]

        entry: Dict[str, Any] = {
            "id": exp_id,
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "task": task,
            "outcome": outcome,
            "solution": solution,
            "errors": errors or [],
            "duration": duration,
            "tags": tags or [],
            "metadata": metadata or {},
        }

        # Append to in-memory list
        self._experiences.append(entry)

        # Append to JSONL file (one JSON object per line)
        try:
            with open(self._long_term_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to write experience to JSONL: %s", exc)

        # Add to vector store if available
        if self._vector_enabled and self._chroma_collection is not None:
            self._add_to_vectors(entry)

        logger.debug("Recorded experience [%s]: %s (%s)", exp_id, task[:60], outcome)
        return entry

    def get_similar_experiences(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find experiences similar to a query string.

        Strategy:
          1. Try ChromaDB vector search (semantic similarity).
          2. If vectors unavailable or empty, fall back to keyword matching.

        Args:
            query: Natural-language description of the current situation.
            top_k: Maximum number of results to return.
            category: Optional filter by task category.
            outcome: Optional filter by outcome ("success", "failure", etc.).

        Returns:
            List of experience dicts ordered by relevance (most relevant first).
        """
        if not self._experiences:
            return []

        # Build optional filter for ChromaDB
        chroma_filter = self._build_chroma_filter(category, outcome)

        # Try vector search first
        if self._vector_enabled and self._chroma_collection is not None:
            try:
                results = self._vector_search(query, top_k, chroma_filter)
                if results:
                    logger.debug("Vector search returned %d results for: %s", len(results), query[:50])
                    return self._apply_outcome_filter(results, outcome)
            except Exception as exc:
                logger.warning("Vector search failed, falling back to keywords: %s", exc)

        # Fallback: keyword matching
        results = self._keyword_search(query, top_k, category, outcome)
        logger.debug("Keyword search returned %d results for: %s", len(results), query[:50])
        return results

    def get_experience_by_id(self, exp_id: str) -> Optional[Dict[str, Any]]:
        """Look up a single experience by its ID."""
        for exp in self._experiences:
            if exp["id"] == exp_id:
                return exp
        return None

    def get_experiences_by_category(
        self, category: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Return experiences filtered by category, newest first."""
        filtered = [e for e in self._experiences if e["category"] == category]
        return filtered[-limit:]

    def get_experience_stats(self) -> Dict[str, Any]:
        """Aggregate statistics over all stored experiences."""
        if not self._experiences:
            return {"total": 0}

        cat_counts: Dict[str, int] = {}
        outcome_counts: Dict[str, int] = {}
        tag_counts: Dict[str, int] = {}
        total_duration = 0.0
        duration_count = 0

        for exp in self._experiences:
            cat = exp.get("category", "unknown")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

            out = exp.get("outcome", "unknown")
            outcome_counts[out] = outcome_counts.get(out, 0) + 1

            for tag in exp.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

            dur = exp.get("duration")
            if dur is not None:
                total_duration += dur
                duration_count += 1

        return {
            "total": len(self._experiences),
            "categories": dict(sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)),
            "outcomes": outcome_counts,
            "top_tags": dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]),
            "avg_duration": round(total_duration / duration_count, 2) if duration_count else None,
            "vector_enabled": self._vector_enabled,
        }

    def prune_experiences(self, max_entries: int = 5000) -> int:
        """Keep only the most recent *max_entries* experiences.

        Rewrites the JSONL file and rebuilds the vector collection.
        Returns the number of entries removed.
        """
        if len(self._experiences) <= max_entries:
            return 0

        removed = len(self._experiences) - max_entries
        self._experiences = self._experiences[-max_entries:]

        # Rewrite JSONL
        self._rewrite_jsonl()

        # Rebuild vector collection
        if self._vector_enabled and self._chroma_collection is not None:
            self._rebuild_vectors()

        logger.info("Pruned %d experiences, %d remaining", removed, len(self._experiences))
        return removed

    # ===================================================================
    # Prompt version management
    # ===================================================================

    def save_prompt_version(
        self,
        version_id: str,
        prompt_text: str,
        trigger: str = "manual",
        reason: str = "",
        parent_version_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Snapshot a prompt version.

        Args:
            version_id: Unique version identifier (e.g. "v1", uuid hex).
            prompt_text: The full system prompt text.
            trigger: What caused this version ("initial", "auto_evolve", "manual", "rollback").
            reason: Human-readable explanation.
            parent_version_id: ID of the previous version (for chain tracking).
            metadata: Arbitrary extra data.

        Returns:
            The version entry dict.
        """
        entry = {
            "version_id": version_id,
            "prompt_text": prompt_text,
            "created_at": datetime.now().isoformat(),
            "trigger": trigger,
            "reason": reason,
            "parent_version_id": parent_version_id,
            "metadata": metadata or {},
            "text_length": len(prompt_text),
        }
        self._prompt_versions.append(entry)
        self._save_prompt_versions()
        logger.info("Saved prompt version '%s' (trigger=%s, len=%d)", version_id, trigger, len(prompt_text))
        return entry

    def get_prompt_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        """Look up a prompt version by ID."""
        for v in self._prompt_versions:
            if v["version_id"] == version_id:
                return v
        return None

    def get_latest_prompt(self) -> Optional[str]:
        """Return the prompt text of the most recently saved version, or None."""
        if not self._prompt_versions:
            return None
        return self._prompt_versions[-1]["prompt_text"]

    def list_prompt_versions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return prompt version entries, newest first.

        Each entry contains version_id, created_at, trigger, reason,
        text_length, and parent_version_id.  The prompt_text itself is
        omitted for brevity; call ``get_prompt_version(id)`` for the full text.
        """
        versions = list(reversed(self._prompt_versions[-limit:]))
        return [
            {
                "version_id": v["version_id"],
                "created_at": v["created_at"],
                "trigger": v["trigger"],
                "reason": v["reason"],
                "parent_version_id": v.get("parent_version_id"),
                "text_length": v.get("text_length", len(v.get("prompt_text", ""))),
            }
            for v in versions
        ]

    # ===================================================================
    # Vector search internals (ChromaDB)
    # ===================================================================

    def _init_vector_store(self, collection_name: str) -> None:
        """Set up ChromaDB persistent client and collection."""
        try:
            chroma_dir = str(self.data_dir / "chroma_db")
            client = chromadb.PersistentClient(
                path=chroma_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._chroma_collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._vector_enabled = True
            logger.info(
                "ChromaDB collection '%s' ready (%d vectors)",
                collection_name, self._chroma_collection.count(),
            )
        except Exception as exc:
            logger.warning("ChromaDB init failed, vector search disabled: %s", exc)
            self._vector_enabled = False
            self._chroma_collection = None

    def _add_to_vectors(self, entry: Dict[str, Any]) -> None:
        """Add a single experience entry to the ChromaDB collection."""
        if self._chroma_collection is None:
            return
        try:
            # Build a text representation for embedding
            doc_text = self._experience_to_text(entry)
            self._chroma_collection.add(
                ids=[entry["id"]],
                documents=[doc_text],
                metadatas=[{
                    "category": entry.get("category", ""),
                    "outcome": entry.get("outcome", ""),
                    "timestamp": entry.get("timestamp", ""),
                    "tags": json.dumps(entry.get("tags", []), ensure_ascii=False),
                }],
            )
        except Exception as exc:
            logger.warning("Failed to add experience to vector store: %s", exc)

    def _vector_search(
        self,
        query: str,
        top_k: int,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Query ChromaDB for similar experiences.

        Returns list of experience dicts ordered by similarity.
        """
        if self._chroma_collection is None or self._chroma_collection.count() == 0:
            return []

        kwargs: Dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(top_k, self._chroma_collection.count()),
        }
        if where:
            kwargs["where"] = where

        results = self._chroma_collection.query(**kwargs)

        # Map IDs back to full experience entries
        matched: List[Dict[str, Any]] = []
        if results and results.get("ids") and results["ids"][0]:
            for exp_id in results["ids"][0]:
                exp = self.get_experience_by_id(exp_id)
                if exp is not None:
                    matched.append(exp)
        return matched

    def _build_chroma_filter(
        self,
        category: Optional[str],
        outcome: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Build a ChromaDB where-filter from optional category/outcome."""
        conditions = []
        if category:
            conditions.append({"category": category})
        if outcome:
            conditions.append({"outcome": outcome})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _apply_outcome_filter(
        self,
        entries: List[Dict[str, Any]],
        outcome: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Post-filter results by outcome if needed."""
        if outcome is None:
            return entries
        return [e for e in entries if e.get("outcome") == outcome]

    def _rebuild_vectors(self) -> None:
        """Delete all vectors and re-add from current experiences."""
        if self._chroma_collection is None:
            return
        try:
            # Delete existing and recreate
            existing_ids = self._chroma_collection.get()["ids"]
            if existing_ids:
                self._chroma_collection.delete(ids=existing_ids)

            for exp in self._experiences:
                self._add_to_vectors(exp)
            logger.info("Rebuilt vector store with %d experiences", len(self._experiences))
        except Exception as exc:
            logger.warning("Failed to rebuild vectors: %s", exc)

    @staticmethod
    def _experience_to_text(entry: Dict[str, Any]) -> str:
        """Convert an experience entry to a searchable text string."""
        parts = [
            f"Task: {entry.get('task', '')}",
            f"Category: {entry.get('category', '')}",
            f"Outcome: {entry.get('outcome', '')}",
        ]
        if entry.get("solution"):
            parts.append(f"Solution: {entry['solution']}")
        if entry.get("errors"):
            parts.append(f"Errors: {'; '.join(entry['errors'])}")
        if entry.get("tags"):
            parts.append(f"Tags: {', '.join(entry['tags'])}")
        return "\n".join(parts)

    # ===================================================================
    # Keyword fallback search
    # ===================================================================

    def _keyword_search(
        self,
        query: str,
        top_k: int,
        category: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Score experiences by keyword overlap with the query.

        Scoring signals:
          - Category exact match (weight 3.0)
          - Shared keywords between query and task+solution text (0.5 each)
          - Substring containment (2.0)
          - Tag overlap (1.0 per tag)
          - Error message keyword overlap (0.8 per keyword)
        """
        query_keywords = self._extract_keywords(query)
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored: List[Tuple[float, Dict[str, Any]]] = []

        for exp in self._experiences:
            score = 0.0

            # Category filter
            if category and exp.get("category") != category:
                continue

            # Outcome filter
            if outcome and exp.get("outcome") != outcome:
                continue

            # Build searchable text from the experience
            exp_text = " ".join([
                exp.get("task", ""),
                exp.get("solution", ""),
                " ".join(exp.get("errors", [])),
            ]).lower()

            exp_keywords = self._extract_keywords(exp_text)

            # Keyword overlap
            overlap = query_keywords & exp_keywords
            if overlap:
                score += len(overlap) * 0.5

            # Substring containment (query inside experience or vice versa)
            if query_lower in exp_text or exp_text in query_lower:
                score += 2.0

            # Word-level containment (short query words found in experience)
            word_hits = sum(1 for w in query_words if w in exp_text and len(w) > 2)
            if word_hits:
                score += word_hits * 0.3

            # Tag overlap
            exp_tags = set(t.lower() for t in exp.get("tags", []))
            tag_overlap = query_keywords & exp_tags
            if tag_overlap:
                score += len(tag_overlap) * 1.0

            # Error-specific keywords (higher weight for error matches)
            for err in exp.get("errors", []):
                err_kw = self._extract_keywords(err.lower())
                err_overlap = query_keywords & err_kw
                if err_overlap:
                    score += len(err_overlap) * 0.8

            # Success bonus: prefer experiences with positive outcomes
            if exp.get("outcome") == "success":
                score += 0.5

            if score > 0:
                scored.append((score, exp))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    @staticmethod
    def _extract_keywords(text: str) -> set:
        """Extract meaningful keywords from text.

        Lowercases, tokenises on word boundaries, filters stop words
        and very short tokens.
        """
        stop_words = {
            "the", "a", "an", "is", "in", "on", "at", "to", "for",
            "of", "and", "or", "not", "was", "were", "been", "be",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "can", "shall", "that",
            "this", "it", "from", "with", "by", "as", "but", "if",
            "are", "be", "into", "than", "then", "so", "no", "up",
            "out", "just", "about", "also", "very", "too", "any",
        }
        words = re.findall(r'[a-z_]\w{2,}', text.lower())
        return {w for w in words if w not in stop_words}

    # ===================================================================
    # Persistence: working memory
    # ===================================================================

    def _load_working(self) -> None:
        """Load working memory from disk."""
        if not self._working_path.exists():
            return
        try:
            data = json.loads(self._working_path.read_text(encoding="utf-8"))
            # Only restore entries with valid timestamps within the last 24 hours
            cutoff = time.time() - 86400
            for key, value in data.items():
                if isinstance(value, dict) and value.get("__ts__", 0) >= cutoff:
                    self._working[key] = value.get("data")
                elif not isinstance(value, dict) or "__ts__" not in value:
                    # Legacy format: store directly
                    self._working[key] = value
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load working memory: %s", exc)

    def _save_working(self) -> None:
        """Persist working memory to disk."""
        data = {}
        for key, value in self._working.items():
            data[key] = {"data": value, "__ts__": time.time()}
        try:
            self._working_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save working memory: %s", exc)

    # ===================================================================
    # Persistence: long-term experiences (JSONL)
    # ===================================================================

    def _load_experiences(self) -> None:
        """Load all experiences from the JSONL file."""
        if not self._long_term_path.exists():
            return
        count = 0
        try:
            with open(self._long_term_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._experiences.append(entry)
                        count += 1
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed JSONL line %d in %s", line_num, self._long_term_path)
        except OSError as exc:
            logger.warning("Failed to load experiences from %s: %s", self._long_term_path, exc)
        logger.debug("Loaded %d experiences from %s", count, self._long_term_path)

    def _rewrite_jsonl(self) -> None:
        """Rewrite the JSONL file with current in-memory experiences."""
        try:
            with open(self._long_term_path, "w", encoding="utf-8") as f:
                for exp in self._experiences:
                    f.write(json.dumps(exp, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to rewrite JSONL: %s", exc)

    # ===================================================================
    # Persistence: prompt versions
    # ===================================================================

    def _load_prompt_versions(self) -> None:
        """Load prompt version history from disk."""
        if not self._prompts_path.exists():
            return
        try:
            data = json.loads(self._prompts_path.read_text(encoding="utf-8"))
            self._prompt_versions = data.get("versions", [])
            logger.debug("Loaded %d prompt versions", len(self._prompt_versions))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load prompt versions: %s", exc)

    def _save_prompt_versions(self) -> None:
        """Persist prompt version history to disk."""
        data = {
            "versions": self._prompt_versions,
            "updated_at": datetime.now().isoformat(),
        }
        try:
            self._prompts_path.parent.mkdir(parents=True, exist_ok=True)
            self._prompts_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save prompt versions: %s", exc)

    # ===================================================================
    # Bulk import / export
    # ===================================================================

    def import_experiences(self, path: str) -> int:
        """Import experiences from another JSONL file.

        Args:
            path: Path to the source JSONL file.

        Returns:
            Number of new experiences imported (duplicates by ID are skipped).
        """
        source = Path(path)
        if not source.exists():
            logger.warning("Import source not found: %s", path)
            return 0

        existing_ids = {exp["id"] for exp in self._experiences}
        imported = 0

        try:
            with open(source, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("id") not in existing_ids:
                            self._experiences.append(entry)
                            existing_ids.add(entry["id"])
                            if self._vector_enabled and self._chroma_collection:
                                self._add_to_vectors(entry)
                            imported += 1
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.warning("Import failed: %s", exc)

        if imported:
            self._rewrite_jsonl()
            logger.info("Imported %d new experiences from %s", imported, path)
        return imported

    def export_experiences(self, path: str) -> int:
        """Export all experiences to a JSONL file.

        Args:
            path: Destination file path.

        Returns:
            Number of experiences written.
        """
        dest = Path(path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                for exp in self._experiences:
                    f.write(json.dumps(exp, ensure_ascii=False) + "\n")
            logger.info("Exported %d experiences to %s", len(self._experiences), path)
        except OSError as exc:
            logger.warning("Export failed: %s", exc)
            return 0
        return len(self._experiences)

    # ===================================================================
    # Diagnostics
    # ===================================================================

    def summary(self) -> Dict[str, Any]:
        """High-level summary of all memory tiers."""
        return {
            "conversation": {
                "messages": len(self._conversation),
                "limit": self._conversation_limit,
            },
            "working_memory": {
                "keys": list(self._working.keys()),
                "count": len(self._working),
            },
            "experiences": self.get_experience_stats(),
            "prompt_versions": {
                "total": len(self._prompt_versions),
                "latest_id": self._prompt_versions[-1]["version_id"] if self._prompt_versions else None,
            },
            "vector_search": {
                "enabled": self._vector_enabled,
                "chromadb_available": _chromadb_available,
            },
        }

    def __repr__(self) -> str:
        return (
            f"MemoryStore(conversation={len(self._conversation)}, "
            f"working={len(self._working)}, "
            f"experiences={len(self._experiences)}, "
            f"prompts={len(self._prompt_versions)}, "
            f"vectors={'ON' if self._vector_enabled else 'OFF'})"
        )


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    import shutil

    tmpdir = tempfile.mkdtemp(prefix="evocoder_mem_")
    try:
        store = MemoryStore(data_dir=tmpdir)

        # ---- Conversation buffer ----
        store.add_conversation("user", "Write a fibonacci function")
        store.add_conversation("assistant", "```python\ndef fib(n):\n    ...\n```")
        store.add_conversation("user", "Add memoization")
        store.add_conversation("assistant", "```python\ndef fib(n, memo={}):\n    ...\n```")

        recent = store.get_recent_conversation(n=4)
        print(f"Recent conversation ({len(recent)} messages):")
        for msg in recent:
            print(f"  [{msg['role']}] {msg['content'][:50]}")

        # ---- Working memory ----
        store.set_working("current_task", "Implement CLI interface")
        store.set_working("active_file", "cli.py")
        print(f"\nWorking memory: {store.get_working_snapshot()}")

        # ---- Experiences ----
        store.record_experience(
            task="Fix KeyError in config loader",
            category="debug",
            outcome="success",
            solution="Used dict.get() with default value instead of direct access",
            errors=["KeyError: 'database_url'"],
            tags=["dict", "key-error", "config"],
            duration=45.0,
        )
        store.record_experience(
            task="Write file upload handler",
            category="code",
            outcome="success",
            solution="Used aiofiles for async file I/O with size validation",
            errors=[],
            tags=["file", "async", "upload"],
            duration=120.0,
        )
        store.record_experience(
            task="Fix import cycle between modules A and B",
            category="refactor",
            outcome="success",
            solution="Moved shared interface to a third module C",
            errors=["ImportError: cannot import name 'X' from partially initialized module"],
            tags=["import", "circular", "refactor"],
            duration=90.0,
        )

        print(f"\nExperience stats: {json.dumps(store.get_experience_stats(), indent=2)}")

        # ---- Similar experiences ----
        similar = store.get_similar_experiences("KeyError when accessing database config", top_k=2)
        print(f"\nSimilar experiences for 'KeyError when accessing database config':")
        for exp in similar:
            print(f"  [{exp['category']}] {exp['task']} -> {exp['solution'][:60]}")

        # ---- Prompt versions ----
        store.save_prompt_version(
            "v1",
            "You are EvoCoder, a coding assistant. Write clean, well-structured code.",
            trigger="initial",
            reason="System initialization",
        )
        store.save_prompt_version(
            "v2",
            "You are EvoCoder, a coding assistant. Write clean code. Handle errors explicitly.",
            trigger="auto_evolve",
            reason="High KeyError rate detected",
            parent_version_id="v1",
        )

        print(f"\nPrompt versions:")
        for v in store.list_prompt_versions():
            print(f"  [{v['version_id']}] {v['trigger']} - {v['reason']} (len={v['text_length']})")
        print(f"Latest prompt: {store.get_latest_prompt()[:80]}...")

        # ---- Full summary ----
        print(f"\nStore summary: {json.dumps(store.summary(), indent=2)}")
        print(f"\nRepr: {store}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print("\nDone. Cleaned up temp directory.")
