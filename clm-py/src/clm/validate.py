"""v3.0 trim-aware validation per ``SPEC.clm`` ``validation.posture.v3.0``.

Mirrors ``clm-rs/src/validate.rs``. A v3.0 document MAY declare in its header::

    ;;; trim.mode: aggressive
    ;;; trim.config: roll_call=10, dream_log=3, decisions_live=8
    ;;; archive.mode: sibling
    ;;; archive.path: <relative-or-absolute-path>

When ``trim.mode != none``, ``archive.path`` MUST be declared and ``archive.mode``
MUST be ``sibling``. When the document has overflowed any trim threshold, the
affected section MUST contain a ``;;`` truncation sentinel BEFORE the kept entries.

Two entry points:

* :func:`validate_v3` — structural validation, no filesystem access.
* :func:`validate_v3_with_filesystem` — additionally resolves and validates the
  sibling archive file (cross-doc sentinel check, archive-shape verification,
  chained archive validation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from clm.document import Document, Section, ParseError


class TrimMode(Enum):
    NONE = "none"
    AGGRESSIVE = "aggressive"


class ArchiveMode(Enum):
    SIBLING = "sibling"
    INLINE = "inline"


DEFAULT_ROLL_CALL_KEEP = 10
DEFAULT_DREAM_LOG_KEEP = 3
DEFAULT_DECISIONS_LIVE_KEEP = 8

_TRIM_CONFIG_KEYS = ("roll_call", "dream_log", "decisions_live")


@dataclass
class TrimConfig:
    roll_call: int = DEFAULT_ROLL_CALL_KEEP
    dream_log: int = DEFAULT_DREAM_LOG_KEEP
    decisions_live: int = DEFAULT_DECISIONS_LIVE_KEEP


@dataclass
class HeaderDeclarations:
    trim_mode: Optional[TrimMode] = None
    trim_config: Optional[TrimConfig] = None
    archive_mode: Optional[ArchiveMode] = None
    archive_path: Optional[str] = None
    archive_path_naming_convention: Optional[str] = None


# ---- diagnostic types ----


@dataclass(frozen=True)
class ValidationError:
    """A spec-conformance error. Mirrors the Rust enum as a tagged dataclass."""

    kind: str
    message: str
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ValidationWarning:
    kind: str
    message: str
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


@dataclass
class ValidationReport:
    header: HeaderDeclarations = field(default_factory=HeaderDeclarations)
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)

    def is_valid(self) -> bool:
        return not self.errors


# ---- public API ----


def validate_v3(doc: Document) -> ValidationReport:
    """Run v3.0 trim-aware validation against a parsed :class:`Document`.

    No filesystem access. Use :func:`validate_v3_with_filesystem` when you can
    resolve ``archive.path`` against a base directory.
    """
    report = ValidationReport()
    report.header = _parse_header_declarations(doc, report.errors, report.warnings)
    _check_trim_mode_consistency(report.header, report.errors, report.warnings)
    _check_delta_session_ids(doc, report.errors, report.warnings)

    if report.header.trim_mode == TrimMode.AGGRESSIVE:
        trim_config = report.header.trim_config or TrimConfig()
        _check_section_sentinels(doc, trim_config, report.errors, report.warnings)

    # Archive-section validation runs regardless of trim.mode (sibling archive files
    # don't carry a trim.mode header). Per SPEC.clm validation.posture.v3.0 these
    # MUST be validated when present.
    _check_archive_section_entries(doc, report.warnings)

    return report


def validate_v3_with_filesystem(doc: Document, base_dir: Path | str) -> ValidationReport:
    """Like :func:`validate_v3` plus filesystem checks on ``archive.path``.

    ``base_dir`` is the directory the ``archive.path`` is resolved against
    (per spec: relative to live file's directory).

    Behavior:
      * state.A (no trim): no filesystem check.
      * state.B (trim declared, no overflow yet): missing archive file → WARNING.
      * state.C (trim declared, overflow occurred): missing or wrong-shape
        archive file → ERROR; archive contents are also validated and any
        diagnostics propagate into the live report.
    """
    report = validate_v3(doc)
    base = Path(base_dir)

    if report.header.trim_mode != TrimMode.AGGRESSIVE:
        return report
    if report.header.archive_path is None:
        return report

    resolved = base / report.header.archive_path
    is_state_c_doc = _is_state_c(doc)

    # Per spec: archive must be a *file*; .exists() returns true for directories.
    if not resolved.is_file():
        if is_state_c_doc:
            report.errors.append(
                ValidationError(
                    kind="archive_file_missing_in_state_c",
                    message=(
                        "doc is in state.C (overflow occurred — sentinel present) but "
                        f"archive.path resolves to {str(resolved)!r} which does not exist"
                    ),
                    details={"resolved_path": str(resolved)},
                )
            )
        else:
            report.warnings.append(
                ValidationWarning(
                    kind="archive_file_not_yet_created_in_state_b",
                    message=(
                        f"archive.path resolves to {str(resolved)!r} which does not exist; "
                        "OK for state.B (file appears at first offload)"
                    ),
                    details={"resolved_path": str(resolved)},
                )
            )
        return report

    # The file exists. Always parse + validate it.
    try:
        archive_text = resolved.read_text()
    except OSError:
        if is_state_c_doc:
            report.errors.append(
                ValidationError(
                    kind="archive_file_missing_in_state_c",
                    message=f"archive.path file at {str(resolved)!r} could not be read",
                    details={"resolved_path": str(resolved)},
                )
            )
        return report

    try:
        archive_doc = Document.parse(archive_text)
    except ParseError:
        if is_state_c_doc:
            report.errors.append(
                ValidationError(
                    kind="archive_file_wrong_shape_in_state_c",
                    message=(
                        f"archive.path resolves to {str(resolved)!r} but the file does not parse "
                        "as a CLM document; state.C requires a real trim archive"
                    ),
                    details={"resolved_path": str(resolved)},
                )
            )
        return report

    # Cross-doc sentinel check: if the archive contains <NAME>.ARCHIVE, the live
    # doc's <NAME> MUST carry the sentinel.
    _cross_check_live_against_archive(doc, archive_doc, report.errors)

    # Chain validate_v3 on archive_doc; propagate diagnostics.
    archive_report = validate_v3(archive_doc)
    report.warnings.extend(archive_report.warnings)
    report.errors.extend(archive_report.errors)

    if is_state_c_doc:
        has_trim_archive_section = any(
            sec.name in {"ROLL.CALL.ARCHIVE", "DREAM.LOG.ARCHIVE", "DECISIONS.ARCHIVE"}
            for sec, _ in archive_doc.sections
        )
        if not has_trim_archive_section:
            report.errors.append(
                ValidationError(
                    kind="archive_file_wrong_shape_in_state_c",
                    message=(
                        f"archive.path resolves to {str(resolved)!r} but the file contains no "
                        "trim ARCHIVE sections "
                        "([ROLL.CALL.ARCHIVE] / [DREAM.LOG.ARCHIVE] / [DECISIONS.ARCHIVE]); "
                        "state.C requires a real trim archive"
                    ),
                    details={"resolved_path": str(resolved)},
                )
            )

    return report


# ---- header parsing ----


def _parse_header_declarations(
    doc: Document,
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> HeaderDeclarations:
    decls = HeaderDeclarations()
    for raw in doc.header:
        if not raw.startswith(";;;"):
            continue
        content = raw[3:]
        for clause in content.split("|"):
            clause = clause.strip()
            if not clause or clause == "---":
                continue
            if ":" not in clause:
                continue
            key, _, value = clause.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "trim.mode":
                if value == "none":
                    decls.trim_mode = TrimMode.NONE
                elif value == "aggressive":
                    decls.trim_mode = TrimMode.AGGRESSIVE
                else:
                    errors.append(
                        ValidationError(
                            kind="unknown_trim_mode",
                            message=f"unknown trim.mode value: {value!r} (expected: none, aggressive)",
                            details={"raw": value},
                        )
                    )
            elif key == "trim.config":
                decls.trim_config = _parse_trim_config(value, errors, warnings)
            elif key == "archive.mode":
                if value == "sibling":
                    decls.archive_mode = ArchiveMode.SIBLING
                elif value == "inline":
                    decls.archive_mode = ArchiveMode.INLINE
                else:
                    errors.append(
                        ValidationError(
                            kind="unknown_archive_mode",
                            message=f"unknown archive.mode value: {value!r} (expected: sibling, inline)",
                            details={"raw": value},
                        )
                    )
            elif key == "archive.path":
                decls.archive_path = value
            elif key == "archive.path.naming.convention":
                decls.archive_path_naming_convention = value
    return decls


def _parse_trim_config(
    value: str,
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> TrimConfig:
    cfg = TrimConfig()
    seen: set[str] = set()
    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            errors.append(
                ValidationError(
                    kind="missing_trim_config_value",
                    message=f"trim.config key {entry!r} has no value",
                    details={"key": entry},
                )
            )
            continue
        k, _, v = entry.partition("=")
        k = k.strip()
        v = v.strip()
        if k in seen:
            errors.append(
                ValidationError(
                    kind="duplicate_trim_config_key",
                    message=f"trim.config has duplicate key: {k!r}",
                    details={"key": k},
                )
            )
            continue
        seen.add(k)
        if not v:
            errors.append(
                ValidationError(
                    kind="missing_trim_config_value",
                    message=f"trim.config key {k!r} has no value",
                    details={"key": k},
                )
            )
            continue
        try:
            n = int(v)
        except ValueError:
            errors.append(
                ValidationError(
                    kind="invalid_trim_config_value",
                    message=f"trim.config[{k!r}] = {v!r} is not a non-negative integer",
                    details={"key": k, "raw": v},
                )
            )
            continue
        if k == "roll_call":
            cfg.roll_call = n
        elif k == "dream_log":
            cfg.dream_log = n
        elif k == "decisions_live":
            cfg.decisions_live = n
        else:
            warnings.append(
                ValidationWarning(
                    kind="unknown_trim_config_key",
                    message=(
                        f"unknown trim.config key {k!r} "
                        f"(recognized: {', '.join(_TRIM_CONFIG_KEYS)}); preserved but ignored"
                    ),
                    details={"key": k},
                )
            )
    return cfg


# ---- section / entry checks ----


def _check_trim_mode_consistency(
    decls: HeaderDeclarations,
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    trim_mode = decls.trim_mode or TrimMode.NONE
    if trim_mode == TrimMode.NONE:
        return
    if decls.archive_path is None:
        errors.append(
            ValidationError(
                kind="missing_archive_path_under_trim",
                message=(
                    "trim.mode is set but ';;; archive.path: ...' header is missing "
                    "(required when trim.mode != none)"
                ),
            )
        )
    if decls.archive_mode == ArchiveMode.INLINE:
        errors.append(
            ValidationError(
                kind="aggressive_trim_with_inline_archive",
                message=(
                    "trim.mode: aggressive cannot be combined with archive.mode: inline "
                    "(unsupported per spec)"
                ),
            )
        )
    elif decls.archive_mode is None:
        warnings.append(
            ValidationWarning(
                kind="archive_mode_unspecified_under_trim",
                message="trim.mode is set but archive.mode is not declared; defaulting to sibling",
            )
        )


def _check_delta_session_ids(
    doc: Document,
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    seen: dict[str, int] = {}
    for section, _ in doc.sections:
        if not section.name.startswith("DELTA."):
            continue
        session_id = section.name[len("DELTA."):]
        # [DELTA.ARCHIVE] is a structural section name used by inline-archive mode.
        if session_id == "ARCHIVE":
            continue
        if not _is_valid_session_id(session_id):
            errors.append(
                ValidationError(
                    kind="invalid_delta_session_id",
                    message=(
                        f"section [{section.name}]: session-id {session_id!r} does not match "
                        "`[a-z0-9][a-z0-9._-]*`"
                    ),
                    details={"section_name": section.name, "session_id": session_id},
                )
            )
            continue
        seen[session_id] = seen.get(session_id, 0) + 1
        if seen[session_id] == 2:
            warnings.append(
                ValidationWarning(
                    kind="duplicate_delta_session_id",
                    message=(
                        f"duplicate [DELTA.session-id] {session_id!r}; "
                        "line order remains authoritative"
                    ),
                    details={"session_id": session_id},
                )
            )


def _check_section_sentinels(
    doc: Document,
    trim: TrimConfig,
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    for section, _ in doc.sections:
        name = section.name
        if name == "ROLL.CALL":
            entries = _count_valid_entries(section.body, "ROLL.CALL", warnings)
            if entries > trim.roll_call and not _has_sentinel(section.body, "ROLL.CALL"):
                errors.append(_sentinel_missing(name, entries, trim.roll_call))
        elif name == "DREAM.LOG":
            entries = _count_valid_entries(section.body, "DREAM.LOG", warnings)
            if entries > trim.dream_log and not _has_sentinel(section.body, "DREAM.LOG"):
                errors.append(_sentinel_missing(name, entries, trim.dream_log))
        elif name == "STATE":
            stats = _decisions_live_stats(section.body)
            # Surface any malformed (quarantined) lines as warnings — same
            # shape as the [ROLL.CALL] / [DREAM.LOG] handling. They are
            # already excluded from `visible_entries` per spec.
            for content in stats.malformed:
                warnings.append(
                    ValidationWarning(
                        kind="malformed_entry",
                        message=(
                            f"[STATE.decisions.live] entry does not match expected shape: {content!r} "
                            "(quarantined; not counted for trim)"
                        ),
                        details={"section": "STATE.decisions.live", "content": content},
                    )
                )
            visible_overflow = stats.visible_entries > trim.decisions_live
            declared_offload = (stats.declared_offload_count or 0) > 0
            if (visible_overflow or declared_offload) and not stats.sentinel_present:
                errors.append(
                    _sentinel_missing("STATE.decisions.live", stats.visible_entries, trim.decisions_live)
                )


def _check_archive_section_entries(
    doc: Document, warnings: list[ValidationWarning]
) -> None:
    for section, _ in doc.sections:
        name = section.name
        if name == "ROLL.CALL.ARCHIVE":
            _count_valid_entries(section.body, "ROLL.CALL.ARCHIVE", warnings)
        elif name == "DREAM.LOG.ARCHIVE":
            _count_valid_entries(section.body, "DREAM.LOG.ARCHIVE", warnings)
        elif name == "DECISIONS.ARCHIVE":
            for line in section.body:
                trimmed = line.strip()
                if not trimmed or trimmed.startswith(";;"):
                    continue
                if not _looks_like_decision_entry(trimmed):
                    warnings.append(
                        ValidationWarning(
                            kind="malformed_entry",
                            message=(
                                f"[DECISIONS.ARCHIVE] entry does not match expected shape: {trimmed!r} "
                                "(quarantined; not counted for trim)"
                            ),
                            details={"section": "DECISIONS.ARCHIVE", "content": trimmed},
                        )
                    )


def _cross_check_live_against_archive(
    live: Document,
    archive: Document,
    errors: list[ValidationError],
) -> None:
    archive_section_names = {sec.name for sec, _ in archive.sections}

    def live_body(name: str) -> Optional[list[str]]:
        for sec, _ in live.sections:
            if sec.name == name:
                return sec.body
        return None

    if "ROLL.CALL.ARCHIVE" in archive_section_names:
        body = live_body("ROLL.CALL")
        if body is not None and not _has_sentinel(body, "ROLL.CALL"):
            entries = sum(
                1 for line in body
                if line.strip() and not line.strip().startswith(";;")
            )
            errors.append(_sentinel_missing("ROLL.CALL", entries, 0))

    if "DREAM.LOG.ARCHIVE" in archive_section_names:
        body = live_body("DREAM.LOG")
        if body is not None and not _has_sentinel(body, "DREAM.LOG"):
            entries = sum(
                1 for line in body
                if line.strip() and not line.strip().startswith(";;")
            )
            errors.append(_sentinel_missing("DREAM.LOG", entries, 0))

    # DECISIONS.ARCHIVE: symmetric to ROLL.CALL.ARCHIVE / DREAM.LOG.ARCHIVE.
    # The intra-doc check in `_check_section_sentinels` only fires on
    # `visible_overflow or declared_offload`, so a state.C doc with bare
    # `decisions.live:` (no `(X of Y archived)`), exactly keep_last visible
    # decisions, and no sentinel — but with a populated sibling
    # [DECISIONS.ARCHIVE] proving offload — would otherwise pass. The
    # archive's existence is stronger evidence than the header parens.
    # (Codex PR-13 round-8 P2-A; resolved in 0.2.1.)
    if "DECISIONS.ARCHIVE" in archive_section_names:
        state_body = live_body("STATE")
        if state_body is not None:
            stats = _decisions_live_stats(state_body)
            # Guard: only fire if a decisions.live: sub-block actually exists in
            # the live doc. Otherwise (e.g. a [STATE] that only carries progress:
            # / next_steps:, or no [STATE] at all), we'd emit a ghost
            # SentinelMissingInTrimmedSection against a section that isn't there
            # — a real false positive caught in code review.
            if stats.block_found and not stats.sentinel_present:
                errors.append(
                    _sentinel_missing("STATE.decisions.live", stats.visible_entries, 0)
                )


# ---- helpers ----


def _is_state_c(doc: Document) -> bool:
    """state.C: at least one trimmed section contains a sentinel OR decisions.live
    declares offload via the (X of Y archived) parenthetical."""
    for section, _ in doc.sections:
        name = section.name
        if name == "ROLL.CALL" and _has_sentinel(section.body, "ROLL.CALL"):
            return True
        if name == "DREAM.LOG" and _has_sentinel(section.body, "DREAM.LOG"):
            return True
        if name == "STATE":
            stats = _decisions_live_stats(section.body)
            if stats.sentinel_present or (stats.declared_offload_count or 0) > 0:
                return True
    return False


def _count_valid_entries(
    body: list[str],
    section_name: str,
    warnings: list[ValidationWarning],
) -> int:
    """Count entries, filtering out malformed lines and emitting MalformedEntry warnings."""
    count = 0
    for line in body:
        trimmed = line.strip()
        if not trimmed or trimmed.startswith(";;"):
            continue
        well_formed = True
        if section_name in ("ROLL.CALL", "ROLL.CALL.ARCHIVE"):
            well_formed = _well_formed_roll_call_line(trimmed)
        elif section_name in ("DREAM.LOG", "DREAM.LOG.ARCHIVE"):
            well_formed = _well_formed_dream_log_line(trimmed)
        if well_formed:
            count += 1
        else:
            warnings.append(
                ValidationWarning(
                    kind="malformed_entry",
                    message=(
                        f"[{section_name}] entry does not match expected shape: {trimmed!r} "
                        "(quarantined; not counted for trim)"
                    ),
                    details={"section": section_name, "content": trimmed},
                )
            )
    return count


def _has_sentinel(body: list[str], section_name: str) -> bool:
    """Sentinel must mention <SECTION>.ARCHIVE + 'offloaded' AND appear BEFORE entries."""
    archive_marker = f"{section_name}.ARCHIVE"
    seen_entry = False
    for line in body:
        t = line.strip()
        if not t:
            continue
        if t.startswith(";;"):
            if not seen_entry and archive_marker in t and "offloaded" in t:
                return True
            continue
        seen_entry = True
    return False


def _sentinel_missing(section: str, entries: int, keep: int) -> ValidationError:
    # The sub-block `STATE.decisions.live` archives to `[DECISIONS.ARCHIVE]`,
    # not `[STATE.decisions.live.ARCHIVE]`. Naive f"{section}.ARCHIVE" produced
    # the wrong example in the hint. Caught in code review.
    archive_marker = (
        "DECISIONS.ARCHIVE" if section == "STATE.decisions.live" else f"{section}.ARCHIVE"
    )
    return ValidationError(
        kind="sentinel_missing_in_trimmed_section",
        message=(
            f"section [{section}] has {entries} entries (keep_last = {keep}); "
            "truncation sentinel is required before kept entries "
            f"(e.g. `;; (oldest N entries offloaded to [{archive_marker}] in sibling)`)"
        ),
        details={"section": section, "entries": entries, "keep": keep},
    )


@dataclass
class _DecisionsLiveStats:
    visible_entries: int = 0
    sentinel_present: bool = False
    declared_offload_count: Optional[int] = None
    # Lines in the decisions.live block that don't match the `dN: ...` shape.
    # Per SPEC.clm `malformed.entry.behavior`: QUARANTINE + WARNING — they are
    # excluded from `visible_entries` so a single broken line cannot push the
    # block over `trim.config.decisions_live` and trigger a false sentinel-missing
    # error. Callers (specifically `_check_section_sentinels`) emit
    # `MalformedEntry` warnings for each.
    malformed: list[str] = field(default_factory=list)
    # Whether a `decisions.live:` header was found in the [STATE] body. Used by
    # the P2-A cross-doc check to avoid emitting a false sentinel-missing error
    # against a sub-block that doesn't exist (e.g. a [STATE] that only carries
    # `progress:` / `next_steps:` but whose sibling archive contains a stale
    # `[DECISIONS.ARCHIVE]` from a prior phase).
    block_found: bool = False


def _decisions_live_stats(state_body: list[str]) -> _DecisionsLiveStats:
    """Inspect [STATE].decisions.live sub-block per SPEC.clm decisions.live.delimitation."""
    stats = _DecisionsLiveStats()
    in_block = False
    block_indent = 0
    seen_entry_yet = False

    for raw in state_body:
        leading = len(raw) - len(raw.lstrip(" "))
        trimmed = raw.lstrip(" ")

        if not in_block:
            if trimmed.startswith("decisions.live"):
                next_char = trimmed[len("decisions.live"):][:1]
                if next_char in (":", "(", " "):
                    in_block = True
                    block_indent = leading
                    stats.block_found = True
                    stats.declared_offload_count = _parse_decisions_live_header_paren(
                        trimmed[len("decisions.live"):]
                    )
            continue

        if not trimmed.strip():
            continue
        if leading <= block_indent:
            break

        if trimmed.startswith(";;"):
            if (
                not seen_entry_yet
                and "DECISIONS.ARCHIVE" in trimmed
                and "offloaded" in trimmed
            ):
                stats.sentinel_present = True
            continue

        # Quarantine malformed lines (anything not `dN: ...`). Per spec they are
        # preserved verbatim, surfaced as warnings, and excluded from the count
        # so a single broken line cannot push the block over the keep_last
        # threshold. (Codex PR-13 round-8 P2-B; resolved in 0.2.1.)
        if not _looks_like_decision_entry(trimmed):
            stats.malformed.append(trimmed)
            continue

        # Note the deliberate asymmetry with `_has_sentinel`: there, ANY
        # non-comment non-blank line terminates the "before-entries" zone.
        # Here, only WELL-FORMED entries do. Spec rationale: the sentinel
        # requirement is `BEFORE the kept entries`, and quarantined malformed
        # lines are not "kept entries." So a sentinel placed after a quarantined
        # line but before any well-formed entry is still valid.
        stats.visible_entries += 1
        seen_entry_yet = True

    return stats


def _parse_decisions_live_header_paren(after_key: str) -> Optional[int]:
    """Parse `(X of Y archived)` or `(last X of Y archived)`. Returns Y - X if Y > X."""
    open_idx = after_key.find("(")
    if open_idx < 0:
        return None
    rest = after_key[open_idx:]
    close_idx = rest.find(")")
    if close_idx < 0:
        return None
    inner = rest[1:close_idx]
    tokens = inner.split()
    i = 0
    if i < len(tokens) and tokens[i] == "last":
        i += 1
    if i + 2 >= len(tokens):
        return None
    try:
        x = int(tokens[i])
        of_kw = tokens[i + 1]
        y = int(tokens[i + 2])
    except ValueError:
        return None
    if of_kw != "of":
        return None
    return y - x if y > x else None


# ---- shape predicates (parser-free regex-equivalent) ----


def _well_formed_roll_call_line(line: str) -> bool:
    """`<Family>.<Model.Version> · <YYYY-MM-DD> · "<note>"`."""
    parts = line.split("·")
    if len(parts) < 3:
        return False
    date = parts[1].strip()
    note = "·".join(parts[2:])
    return _looks_like_iso_date(date) and '"' in note


def _well_formed_dream_log_line(line: str) -> bool:
    """`<YYYY-MM-DD[ <session-tag>]?> | <Family>.<Model.Version> | <message>`."""
    parts = line.split("|")
    if len(parts) < 3:
        return False
    first = parts[0].strip()
    date_token = first.split()[0] if first.split() else ""
    return _looks_like_iso_date(date_token)


_ASCII_DIGITS = frozenset("0123456789")


def _is_ascii_digit_run(s: str) -> bool:
    """ASCII-digits-only check. Rust uses ``b.is_ascii_digit()`` and JS uses ``\\d``
    (no ``u`` flag). Python's ``str.isdigit()`` accepts non-ASCII digits like Thai
    ``\\u0e50`` and Arabic-Indic ``\\u0660`` — diverges from the other impls."""
    return bool(s) and all(c in _ASCII_DIGITS for c in s)


def _looks_like_iso_date(s: str) -> bool:
    if len(s) != 10:
        return False
    return (
        _is_ascii_digit_run(s[0:4])
        and s[4] == "-"
        and _is_ascii_digit_run(s[5:7])
        and s[7] == "-"
        and _is_ascii_digit_run(s[8:10])
    )


def _looks_like_decision_entry(line: str) -> bool:
    """`dN: text [session N]` shape — loose: just `d<digit>` prefix and `:` separator."""
    if len(line) < 3 or line[0] != "d" or line[1] not in _ASCII_DIGITS:
        return False
    return ":" in line


def _is_valid_session_id(s: str) -> bool:
    """Per spec: ``[a-z0-9][a-z0-9._-]*``."""
    if not s:
        return False
    first = s[0]
    if not (first.isascii() and (first.islower() or first.isdigit())):
        return False
    return all(
        c.isascii() and (c.islower() or c.isdigit() or c in "._-")
        for c in s[1:]
    )


__all__ = [
    "ArchiveMode",
    "DEFAULT_DECISIONS_LIVE_KEEP",
    "DEFAULT_DREAM_LOG_KEEP",
    "DEFAULT_ROLL_CALL_KEEP",
    "HeaderDeclarations",
    "TrimConfig",
    "TrimMode",
    "ValidationError",
    "ValidationReport",
    "ValidationWarning",
    "validate_v3",
    "validate_v3_with_filesystem",
]
