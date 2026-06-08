"""
UserPreferences - Learns and remembers the user's coding style preferences.

Part of EvoCoder's self-improvement system.  Observes code the user writes
and explicit feedback they give, then builds a persistent preference profile
that shapes future code generation to match their style.

The three core operations are:

  learn_from_code    -- analyse a code sample and extract style signals
  learn_from_feedback -- incorporate explicit user feedback about style
  get_style_prompt   -- return a style guide string for the LLM prompt

Detected dimensions:
  - Indent style (spaces vs tabs, width)
  - Quote style (single vs double)
  - Trailing comma preference
  - Import style (absolute vs relative, grouping)
  - Naming conventions (snake_case, camelCase, PascalCase)
  - Line length preference
  - Docstring style (Google, NumPy, Sphinx, none)
  - Type hint usage (none, partial, full)
  - Library preferences (which libraries the user favours)
"""

import json
import re
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("evocoder.evolution.user_prefs")


# ---------------------------------------------------------------------------
# Defaults (used when no data has been collected yet)
# ---------------------------------------------------------------------------

_DEFAULT_PREFS: dict = {
    "indent_style": "spaces",
    "indent_width": 4,
    "quote_style": "double",
    "trailing_comma": True,
    "import_style": "absolute",
    "import_grouping": True,
    "naming_convention": "snake_case",
    "max_line_length": 88,
    "docstring_style": "google",
    "type_hints": "partial",
    "preferred_libraries": {},
    "avoided_libraries": [],
    "single_letter_vars": False,
    "blank_lines_top_level": 2,
    "blank_lines_inner": 1,
    "trailing_newline": True,
}


class UserPreferences:
    """Learns and persists the user's coding style preferences.

    Usage::

        prefs = UserPreferences()
        prefs.learn_from_code(open("my_module.py").read())
        prefs.learn_from_feedback("I prefer single quotes")

        style = prefs.get_style_prompt()
        # -> "Use 4-space indentation. Use single quotes. ..."

    The profile is saved to disk after every mutation so it survives restarts.
    """

    def __init__(self, memory_path: str = "user_prefs.json"):
        self.memory_path = Path(memory_path)
        self.prefs: dict = dict(_DEFAULT_PREFS)
        self.observations: list[dict] = []
        self.feedback_log: list[dict] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load preferences from disk.  Missing file is not an error."""
        if not self.memory_path.exists():
            return
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "prefs" in data:
                # Merge loaded prefs over defaults so new fields get defaults
                merged = dict(_DEFAULT_PREFS)
                merged.update(data["prefs"])
                self.prefs = merged
            self.observations = data.get("observations", [])
            self.feedback_log = data.get("feedback_log", [])
            logger.info("Loaded user preferences from %s", self.memory_path)
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to load user prefs: %s", exc)

    def _save(self) -> None:
        """Persist the full preference state to disk."""
        data = {
            "prefs": self.prefs,
            "observations": self.observations[-200:],  # cap history
            "feedback_log": self.feedback_log[-100:],
            "updated_at": datetime.now().isoformat(),
        }
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.warning("Failed to save user prefs: %s", exc)

    # ------------------------------------------------------------------
    # Public API: learn_from_code
    # ------------------------------------------------------------------

    def learn_from_code(self, code: str, source: str = "observation") -> dict:
        """Analyse a code sample and update the preference profile.

        Extracts style signals from the code, records them as an observation,
        and recalculates the dominant preference for each dimension using
        weighted voting across all observations.

        Args:
            code: The source code text to analyse.
            source: Where this sample came from (e.g. "user_input", "repo").

        Returns:
            A dict of the style signals detected in this sample.
        """
        signals = self._extract_signals(code)

        observation = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "signals": signals,
            "lines_of_code": len(code.splitlines()),
        }
        self.observations.append(observation)
        self._recalculate_prefs()
        self._save()

        logger.debug("Learned from code (%d lines): %s", observation["lines_of_code"], signals)
        return signals

    # ------------------------------------------------------------------
    # Public API: learn_from_feedback
    # ------------------------------------------------------------------

    def learn_from_feedback(self, feedback: str) -> dict:
        """Parse explicit user feedback and apply it to the preference profile.

        Supports natural-language feedback like:
          - "I prefer single quotes"
          - "Use tabs instead of spaces"
          - "Use 2-space indentation"
          - "I like type hints everywhere"
          - "Please use black formatting"
          - "I prefer f-strings over .format()"
          - "Don't use numpy, use pure python"

        Args:
            feedback: Free-text feedback from the user.

        Returns:
            Dict of preference changes that were applied.
        """
        changes: dict = {}
        lower = feedback.lower().strip()

        # ---- Indent style ----
        if re.search(r'\btab', lower):
            if self.prefs["indent_style"] != "tabs":
                self.prefs["indent_style"] = "tabs"
                changes["indent_style"] = "tabs"
        elif re.search(r'\bspace', lower):
            if self.prefs["indent_style"] != "spaces":
                self.prefs["indent_style"] = "spaces"
                changes["indent_style"] = "spaces"

        # Indent width: "2-space", "4 space", "2 spaces", "indent width of 2"
        width_match = re.search(
            r'(\d)[\s-]?space|indent(?:ation)?(?:\s+(?:width|level))?\s*(?:of|is|=|:)?\s*(\d)',
            lower,
        )
        if width_match:
            w = int(width_match.group(1) or width_match.group(2))
            if w in (1, 2, 3, 4, 8):
                if self.prefs["indent_width"] != w:
                    self.prefs["indent_width"] = w
                    changes["indent_width"] = w

        # ---- Quote style ----
        if re.search(r'\bsingle\s+quote', lower):
            if self.prefs["quote_style"] != "single":
                self.prefs["quote_style"] = "single"
                changes["quote_style"] = "single"
        elif re.search(r'\bdouble\s+quote', lower):
            if self.prefs["quote_style"] != "double":
                self.prefs["quote_style"] = "double"
                changes["quote_style"] = "double"

        # ---- Trailing comma ----
        if re.search(r'\bno\s+trailing\s+comma|without\s+trailing\s+comma', lower):
            if self.prefs["trailing_comma"]:
                self.prefs["trailing_comma"] = False
                changes["trailing_comma"] = False
        elif re.search(r'\btrailing\s+comma', lower):
            if not self.prefs["trailing_comma"]:
                self.prefs["trailing_comma"] = True
                changes["trailing_comma"] = True

        # ---- Import style ----
        if re.search(r'\brelative\s+import', lower):
            if self.prefs["import_style"] != "relative":
                self.prefs["import_style"] = "relative"
                changes["import_style"] = "relative"
        elif re.search(r'\babsolute\s+import', lower):
            if self.prefs["import_style"] != "absolute":
                self.prefs["import_style"] = "absolute"
                changes["import_style"] = "absolute"

        # ---- Type hints ----
        if re.search(r'\btype\s*hints?\s*(everywhere|full|always|all)|full\s+type\s+hint', lower):
            if self.prefs["type_hints"] != "full":
                self.prefs["type_hints"] = "full"
                changes["type_hints"] = "full"
        elif re.search(r'\bno\s+type\s*hints?|without\s+type\s*hints?|skip\s+type\s*hints?', lower):
            if self.prefs["type_hints"] != "none":
                self.prefs["type_hints"] = "none"
                changes["type_hints"] = "none"
        elif re.search(r'\btype\s*hint', lower):
            if self.prefs["type_hints"] != "partial":
                self.prefs["type_hints"] = "partial"
                changes["type_hints"] = "partial"

        # ---- Line length ----
        len_match = re.search(r'(?:line\s*(?:length|width)|max(?:imum)?\s*line)\s*(?:of|is|=|:)?\s*(\d+)', lower)
        if len_match:
            ll = int(len_match.group(1))
            if 40 <= ll <= 200:
                if self.prefs["max_line_length"] != ll:
                    self.prefs["max_line_length"] = ll
                    changes["max_line_length"] = ll

        # ---- Docstring style ----
        for style_name in ("google", "numpy", "sphinx", "epytext"):
            if style_name in lower and "docstring" in lower:
                if self.prefs["docstring_style"] != style_name:
                    self.prefs["docstring_style"] = style_name
                    changes["docstring_style"] = style_name
                break
        if re.search(r'\bno\s+docstring|skip\s+docstring|without\s+docstring', lower):
            if self.prefs["docstring_style"] != "none":
                self.prefs["docstring_style"] = "none"
                changes["docstring_style"] = "none"

        # ---- Library preferences ----
        # "prefer X", "use X", "I like X"  (but not "prefer single quotes" etc.)
        _style_words = {
            "single", "double", "space", "spaces", "tab", "tabs",
            "type", "hint", "hints", "import", "imports", "comma",
            "commas", "trailing", "line", "lines", "docstring",
            "snake_case", "camelcase", "pascalcase",
        }
        lib_match = re.search(
            r'(?:prefer|like|favour|favor)\s+([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)',
            lower,
        )
        if lib_match and lib_match.group(1) in _style_words:
            lib_match = None
        if not lib_match:
            lib_match = re.search(
                r'\buse\s+([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)',
                lower,
            )
            if lib_match and lib_match.group(1) in _style_words:
                lib_match = None
        if lib_match:
            lib = lib_match.group(1)
            if lib not in ("the", "a", "an", "my", "this", "that", "it"):
                self.prefs["preferred_libraries"][lib] = (
                    self.prefs["preferred_libraries"].get(lib, 0) + 1
                )
                changes["preferred_library"] = lib

        # "don't use X", "avoid X", "no X"
        avoid_match = re.search(
            r"(?:don'?t\s+use|avoid|no\s+more?|stop\s+using|not?\s+use)\s+([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)",
            lower,
        )
        if avoid_match:
            lib = avoid_match.group(1)
            if lib not in ("the", "a", "an", "my", "this", "that", "it"):
                if lib not in self.prefs["avoided_libraries"]:
                    self.prefs["avoided_libraries"].append(lib)
                # Remove from preferred if present
                self.prefs["preferred_libraries"].pop(lib, None)
                changes["avoided_library"] = lib

        # ---- Black formatting ----
        if re.search(r'\bblack\b', lower) and re.search(r'format|style|use', lower):
            self.prefs["indent_width"] = 4
            self.prefs["quote_style"] = "double"
            self.prefs["max_line_length"] = 88
            self.prefs["trailing_comma"] = True
            changes["formatter"] = "black"

        # Log feedback
        entry = {
            "timestamp": datetime.now().isoformat(),
            "feedback": feedback,
            "changes": changes,
        }
        self.feedback_log.append(entry)

        if changes:
            self._save()
            logger.info("Applied feedback changes: %s", changes)
        else:
            logger.debug("No preference changes detected from feedback: %s", feedback)

        return changes

    # ------------------------------------------------------------------
    # Public API: get_style_prompt
    # ------------------------------------------------------------------

    def get_style_prompt(self, task_type: str = "general") -> str:
        """Build a style-guide string suitable for injection into an LLM prompt.

        Args:
            task_type: The kind of task being performed (e.g. "code", "refactor").
                       Used to adjust emphasis (e.g. more type hints for library code).

        Returns:
            A multi-line style guide string.  Empty if only defaults are active.
        """
        parts: list[str] = []

        p = self.prefs

        # Indentation
        if p["indent_style"] == "tabs":
            parts.append("Use tabs for indentation.")
        else:
            parts.append(f"Use {p['indent_width']}-space indentation.")

        # Quotes
        if p["quote_style"] == "single":
            parts.append("Use single quotes for strings.")
        else:
            parts.append('Use double quotes for strings.')

        # Trailing commas
        if p["trailing_comma"]:
            parts.append("Use trailing commas in multi-line collections.")
        else:
            parts.append("Do not use trailing commas.")

        # Imports
        if p["import_style"] == "relative":
            parts.append("Use relative imports within the package.")
        else:
            parts.append("Use absolute imports.")
        if p["import_grouping"]:
            parts.append("Group imports: stdlib, third-party, local.")

        # Line length
        parts.append(f"Keep lines under {p['max_line_length']} characters.")

        # Naming
        parts.append(f"Use {p['naming_convention']} for identifiers.")

        # Type hints
        hint_level = p["type_hints"]
        if hint_level == "full":
            parts.append("Add type hints to all function signatures and return types.")
        elif hint_level == "partial":
            parts.append("Add type hints to public function signatures.")
        # "none" -> omit

        # Docstrings
        ds = p["docstring_style"]
        if ds == "none":
            parts.append("Omit docstrings unless the function is complex.")
        elif ds in ("google", "numpy", "sphinx", "epytext"):
            parts.append(f"Write docstrings in {ds.capitalize()} style.")

        # Blank lines
        parts.append(
            f"Use {p['blank_lines_top_level']} blank lines between top-level definitions "
            f"and {p['blank_lines_inner']} blank line(s) between methods."
        )

        # Trailing newline
        if p["trailing_newline"]:
            parts.append("Ensure files end with a trailing newline.")

        # Library preferences
        preferred = p.get("preferred_libraries", {})
        if preferred:
            top = sorted(preferred.items(), key=lambda x: x[1], reverse=True)[:5]
            libs = ", ".join(lib for lib, _ in top)
            parts.append(f"Prefer these libraries when applicable: {libs}.")

        avoided = p.get("avoided_libraries", [])
        if avoided:
            libs = ", ".join(avoided[:5])
            parts.append(f"Avoid using: {libs}.")

        # Task-type adjustments
        if task_type == "library" and hint_level != "full":
            parts.append("(For library code: add comprehensive type hints.)")
        if task_type == "script" and hint_level == "full":
            parts.append("(For quick scripts: type hints on public API only.)")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Internal: signal extraction from code
    # ------------------------------------------------------------------

    def _extract_signals(self, code: str) -> dict:
        """Extract style signals from a code sample.

        Returns a dict with keys matching the preference dimensions.
        """
        signals: dict = {}

        lines = code.splitlines()
        if not lines:
            return signals

        # ---- Indent style and width ----
        indent_counts: Counter = Counter()
        tab_lines = 0
        for line in lines:
            if not line or line[0] not in (" ", "\t"):
                continue
            if line[0] == "\t":
                tab_lines += 1
            else:
                match = re.match(r'^( +)', line)
                if match:
                    indent_counts[len(match.group(1))] += 1

        if tab_lines > sum(indent_counts.values()):
            signals["indent_style"] = "tabs"
        else:
            signals["indent_style"] = "spaces"
            # Find the most common indent width (GCD of common widths)
            if indent_counts:
                widths = sorted(indent_counts.keys())
                signals["indent_width"] = self._guess_indent_width(widths, indent_counts)

        # ---- Quote style ----
        single_q = len(re.findall(r"(?<![\\])'", code))
        double_q = len(re.findall(r'(?<![\\])"', code))
        if single_q + double_q > 0:
            signals["quote_style"] = "single" if single_q > double_q else "double"

        # ---- Trailing commas ----
        multi_line_lists = re.findall(r'\[[\s\S]*?\]', code)
        multi_line_dicts = re.findall(r'\{[\s\S]*?\}', code)
        trailing_count = 0
        total_multi = 0
        for block in multi_line_lists + multi_line_dicts:
            if "\n" in block:
                total_multi += 1
                stripped = block.rstrip()
                if stripped.endswith(","):
                    trailing_count += 1
        if total_multi > 0:
            signals["trailing_comma"] = trailing_count / total_multi > 0.5

        # ---- Import style ----
        relative_imports = len(re.findall(r'^from\s+\.', code, re.MULTILINE))
        absolute_imports = len(re.findall(r'^import\s|^from\s+[^.]', code, re.MULTILINE))
        if relative_imports + absolute_imports > 0:
            signals["import_style"] = "relative" if relative_imports > absolute_imports else "absolute"

        # Check for import grouping (blank lines between import blocks)
        import_section = re.findall(
            r'^(?:import\s|from\s).*$', code, re.MULTILINE
        )
        if len(import_section) >= 3:
            # Look for blank lines within import blocks
            in_imports = False
            has_grouping = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    in_imports = True
                elif in_imports and stripped == "":
                    has_grouping = True
                elif in_imports and not stripped.startswith(("import ", "from ")):
                    break
            signals["import_grouping"] = has_grouping

        # ---- Naming convention ----
        func_names = re.findall(r'def\s+([a-zA-Z_]\w*)', code)
        class_names = re.findall(r'class\s+([a-zA-Z_]\w*)', code)
        var_names = re.findall(r'^([a-zA-Z_]\w*)\s*=', code, re.MULTILINE)

        conventions = Counter()
        for name in func_names + var_names:
            if "_" in name and name == name.lower():
                conventions["snake_case"] += 1
            elif name[0].islower() and not "_" in name and any(c.isupper() for c in name[1:]):
                conventions["camelCase"] += 1
        for name in class_names:
            if name[0].isupper():
                conventions["PascalCase"] += 1

        if conventions:
            signals["naming_convention"] = conventions.most_common(1)[0][0]

        # ---- Line length ----
        non_empty = [len(line) for line in lines if line.strip()]
        if non_empty:
            # Use 90th percentile as the "preferred" max
            sorted_lengths = sorted(non_empty)
            idx = int(len(sorted_lengths) * 0.9)
            signals["max_line_length"] = sorted_lengths[min(idx, len(sorted_lengths) - 1)]

        # ---- Type hints ----
        func_defs = re.findall(r'def\s+\w+\(.*?\)(?:\s*->.*)?:', code, re.DOTALL)
        funcs_with_hints = len(re.findall(r'->\s*\w', code))
        funcs_with_param_hints = len(re.findall(r':\s*(?:int|str|float|bool|list|dict|tuple|set|None|Optional|Any|Union|List|Dict|Tuple|Set)\b', code))

        if func_defs:
            total_funcs = len(func_defs)
            hint_ratio = (funcs_with_hints + funcs_with_param_hints) / (total_funcs * 2)  # rough
            if hint_ratio > 0.7:
                signals["type_hints"] = "full"
            elif hint_ratio > 0.2:
                signals["type_hints"] = "partial"
            else:
                signals["type_hints"] = "none"

        # ---- Docstring style ----
        docstrings = re.findall(r'"""[\s\S]*?"""', code)
        if not docstrings:
            docstrings = re.findall(r"'''[\s\S]*?'''", code)
        if docstrings:
            sample = docstrings[0]
            if re.search(r'Args:|Returns:|Raises:', sample):
                signals["docstring_style"] = "google"
            elif re.search(r'Parameters\s*\n\s*-{3,}', sample):
                signals["docstring_style"] = "numpy"
            elif re.search(r':param\s|:returns?:|:rtype:', sample):
                signals["docstring_style"] = "sphinx"
            else:
                signals["docstring_style"] = "google"  # default assumption

        # ---- Single-letter variable tolerance ----
        single_letter = re.findall(r'\b([a-zA-Z])\s*=\s*(?!=)', code)
        multi_letter = re.findall(r'\b([a-zA-Z_]{2,})\s*=\s*(?!=)', code)
        if single_letter and multi_letter:
            ratio = len(single_letter) / (len(single_letter) + len(multi_letter))
            signals["single_letter_vars"] = ratio > 0.3

        # ---- Library usage ----
        import_names = re.findall(r'^import\s+(\S+)|^from\s+(\S+)\s+import', code, re.MULTILINE)
        libs_used = []
        for imp_from, imp_what in import_names:
            lib = imp_from or imp_what
            lib = lib.split(".")[0]  # top-level package
            if lib not in ("__future__",):
                libs_used.append(lib)
        if libs_used:
            signals["libraries_used"] = libs_used

        return signals

    def _guess_indent_width(self, widths: list[int], counts: Counter) -> int:
        """Guess the most likely indent width from observed indent levels."""
        if not widths:
            return 4

        # If there's a clear winner
        if len(widths) == 1:
            w = widths[0]
            # Normalize to common values
            for candidate in (2, 4, 8):
                if w % candidate == 0:
                    return candidate
            return w

        # Find GCD of the most common widths
        from math import gcd
        from functools import reduce

        # Weight by frequency
        weighted_widths = []
        for w in widths:
            weighted_widths.extend([w] * counts[w])

        if weighted_widths:
            g = reduce(gcd, weighted_widths)
            # Normalize GCD to common indent widths
            for candidate in (2, 4, 8):
                if g == candidate:
                    return candidate
            if g in (1, 3, 5, 6, 7):
                # Odd GCD usually means 4-space with alignment
                return 4
            return g if g <= 8 else 4

        return 4

    # ------------------------------------------------------------------
    # Internal: preference recalculation
    # ------------------------------------------------------------------

    def _recalculate_prefs(self) -> None:
        """Recalculate preferences from all observations using weighted voting.

        More recent observations carry more weight (linear decay).
        """
        if not self.observations:
            return

        n = len(self.observations)

        # Collect weighted votes for each dimension
        vote_indent_style: Counter = Counter()
        vote_indent_width: Counter = Counter()
        vote_quote_style: Counter = Counter()
        vote_trailing_comma: Counter = Counter()
        vote_import_style: Counter = Counter()
        vote_type_hints: Counter = Counter()
        vote_docstring_style: Counter = Counter()
        vote_max_line_length: list[int] = []
        vote_naming: Counter = Counter()

        for i, obs in enumerate(self.observations):
            weight = (i + 1) / n  # more recent = higher weight
            sig = obs.get("signals", {})

            if "indent_style" in sig:
                vote_indent_style[sig["indent_style"]] += weight
            if "indent_width" in sig:
                vote_indent_width[sig["indent_width"]] += weight
            if "quote_style" in sig:
                vote_quote_style[sig["quote_style"]] += weight
            if "trailing_comma" in sig:
                vote_trailing_comma[sig["trailing_comma"]] += weight
            if "import_style" in sig:
                vote_import_style[sig["import_style"]] += weight
            if "type_hints" in sig:
                vote_type_hints[sig["type_hints"]] += weight
            if "docstring_style" in sig:
                vote_docstring_style[sig["docstring_style"]] += weight
            if "max_line_length" in sig:
                vote_max_line_length.append(sig["max_line_length"])
            if "naming_convention" in sig:
                vote_naming[sig["naming_convention"]] += weight
            if "libraries_used" in sig:
                for lib in sig["libraries_used"]:
                    self.prefs["preferred_libraries"][lib] = (
                        self.prefs["preferred_libraries"].get(lib, 0) + weight
                    )

        def winner(counter: Counter) -> Optional[str]:
            if not counter:
                return None
            return counter.most_common(1)[0][0]

        def winner_num(counter: Counter) -> Optional[int]:
            if not counter:
                return None
            return counter.most_common(1)[0][0]

        # Apply winners, but feedback overrides are preserved (they have
        # been written directly to self.prefs and won't be overwritten
        # if there's no observation data for that dimension).
        for dim, votes in [
            ("indent_style", vote_indent_style),
            ("quote_style", vote_quote_style),
            ("import_style", vote_import_style),
            ("type_hints", vote_type_hints),
            ("docstring_style", vote_docstring_style),
            ("naming_convention", vote_naming),
        ]:
            w = winner(votes)
            if w is not None:
                self.prefs[dim] = w

        w = winner_num(vote_indent_width)
        if w is not None:
            self.prefs["indent_width"] = w

        w = winner(vote_trailing_comma)
        if w is not None:
            self.prefs["trailing_comma"] = w

        # Line length: use median of observations
        if vote_max_line_length:
            vote_max_line_length.sort()
            mid = len(vote_max_line_length) // 2
            self.prefs["max_line_length"] = vote_max_line_length[mid]

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        """Get a single preference value."""
        return self.prefs.get(key, default)

    def get_all(self) -> dict:
        """Return a copy of the full preference dict."""
        return dict(self.prefs)

    def observation_count(self) -> int:
        """How many code samples have been observed."""
        return len(self.observations)

    def feedback_count(self) -> int:
        """How many explicit feedback entries have been recorded."""
        return len(self.feedback_log)

    def summary(self) -> dict:
        """High-level summary of the preference profile."""
        return {
            "indent": f"{self.prefs['indent_style']} ({self.prefs['indent_width']})",
            "quotes": self.prefs["quote_style"],
            "trailing_comma": self.prefs["trailing_comma"],
            "line_length": self.prefs["max_line_length"],
            "type_hints": self.prefs["type_hints"],
            "docstring_style": self.prefs["docstring_style"],
            "naming": self.prefs["naming_convention"],
            "top_libraries": sorted(
                self.prefs.get("preferred_libraries", {}).items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5],
            "avoided_libraries": self.prefs.get("avoided_libraries", []),
            "observations": len(self.observations),
            "feedback_entries": len(self.feedback_log),
        }

    def reset(self) -> None:
        """Reset all preferences back to defaults and clear history."""
        self.prefs = dict(_DEFAULT_PREFS)
        self.observations.clear()
        self.feedback_log.clear()
        self._save()
        logger.info("User preferences reset to defaults")

    def __repr__(self) -> str:
        return (
            f"UserPreferences(indent={self.prefs['indent_style']}/{self.prefs['indent_width']}, "
            f"quotes={self.prefs['quote_style']}, "
            f"observations={len(self.observations)}, "
            f"feedback={len(self.feedback_log)})"
        )


# ---------------------------------------------------------------------------
# Quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    prefs = UserPreferences("test_user_prefs.json")

    # Demo: learn from code
    sample = '''
import os
import sys

from pathlib import Path


def calculate_total(items: list[dict]) -> float:
    """Calculate the total price.

    Args:
        items: List of item dicts with 'price' key.

    Returns:
        Sum of all prices.
    """
    total = 0.0
    for item in items:
        total += item['price']
    return total


class DataProcessor:
    def __init__(self, config: dict):
        self.config = config
        self._cache: dict = {}

    def process(self, raw_data: str) -> dict:
        # Process raw input and return structured result.
        return {"status": "ok", "data": raw_data}
'''
    signals = prefs.learn_from_code(sample, source="demo")
    print("Detected signals:")
    for k, v in signals.items():
        if k != "libraries_used":
            print(f"  {k}: {v}")

    # Demo: learn from feedback
    changes = prefs.learn_from_feedback("I prefer single quotes and 2-space indentation")
    print(f"\nFeedback changes: {changes}")

    changes = prefs.learn_from_feedback("Don't use requests anymore, use httpx")
    print(f"Feedback changes: {changes}")

    # Demo: get style prompt
    prompt = prefs.get_style_prompt(task_type="code")
    print(f"\nStyle prompt:\n{prompt}")

    # Summary
    print(f"\nSummary: {json.dumps(prefs.summary(), indent=2)}")

    # Cleanup
    prefs.memory_path.unlink(missing_ok=True)
    print("\nDone. Cleaned up test file.")
