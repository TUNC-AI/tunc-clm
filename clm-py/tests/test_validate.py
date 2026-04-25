"""Mirror of clm-rs/src/validate.rs unit tests + the regression cases."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from clm import (
    Document,
    ValidationError,
    ValidationWarning,
    validate_v3,
    validate_v3_with_filesystem,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text()


def _doc_with_header(extra: list[str]) -> Document:
    text = ";;; CLM/3.0 — test\n;;; test.clm\n"
    for line in extra:
        text += f";;; {line}\n"
    text += ";;; ---\n\n[STATE]\n  ;; empty\n;;\n\n;;; EOF | CLM/3.0\n"
    return Document.parse(text)


def _has_error(report, kind: str) -> bool:
    return any(e.kind == kind for e in report.errors)


def _has_warning(report, kind: str) -> bool:
    return any(w.kind == kind for w in report.warnings)


def test_no_trim_no_errors() -> None:
    report = validate_v3(_doc_with_header([]))
    assert report.errors == []


def test_trim_aggressive_without_archive_path_is_error() -> None:
    report = validate_v3(_doc_with_header(["trim.mode: aggressive", "archive.mode: sibling"]))
    assert _has_error(report, "missing_archive_path_under_trim")


def test_trim_aggressive_with_inline_archive_is_error() -> None:
    report = validate_v3(
        _doc_with_header(
            ["trim.mode: aggressive", "archive.mode: inline", "archive.path: foo.archive.clm"]
        )
    )
    assert _has_error(report, "aggressive_trim_with_inline_archive")


def test_trim_aggressive_archive_mode_unspecified_warns() -> None:
    report = validate_v3(_doc_with_header(["trim.mode: aggressive", "archive.path: foo.archive.clm"]))
    assert _has_warning(report, "archive_mode_unspecified_under_trim")


def test_duplicate_trim_config_key_is_error() -> None:
    report = validate_v3(
        _doc_with_header(
            [
                "trim.mode: aggressive",
                "archive.mode: sibling",
                "archive.path: foo.archive.clm",
                "trim.config: roll_call=10, roll_call=12",
            ]
        )
    )
    assert _has_error(report, "duplicate_trim_config_key")


def test_unknown_trim_config_key_warns() -> None:
    report = validate_v3(
        _doc_with_header(
            [
                "trim.mode: aggressive",
                "archive.mode: sibling",
                "archive.path: foo.archive.clm",
                "trim.config: roll_call=10, mystery=99",
            ]
        )
    )
    assert _has_warning(report, "unknown_trim_config_key")


def test_unknown_trim_mode_is_error() -> None:
    report = validate_v3(_doc_with_header(["trim.mode: yolo"]))
    assert _has_error(report, "unknown_trim_mode")


def test_missing_sentinel_when_overflowing_is_error() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n"
        ";;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        '  CLd.Snt4.6 · 2026-04-07 · "a"\n'
        '  CLd.Ops4.6 · 2026-04-07 · "b"\n'
        '  CLd.Snt4.5 · 2026-04-24 · "c"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert _has_error(report, "sentinel_missing_in_trimmed_section")


def test_sentinel_present_when_overflowing_is_ok() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n"
        ";;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        "  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n"
        '  CLd.Ops4.6 · 2026-04-07 · "b"\n'
        '  CLd.Snt4.5 · 2026-04-24 · "c"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert not _has_error(report, "sentinel_missing_in_trimmed_section")


def test_invalid_delta_session_id_is_error() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n"
        "[STATE]\n  ;; empty\n;;\n\n"
        "[DELTA.UPPER]\n  body\n;;\n\n"
        ";;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert _has_error(report, "invalid_delta_session_id")


def test_duplicate_delta_session_id_warns() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n"
        "[STATE]\n  ;; empty\n;;\n\n"
        "[DELTA.session-1]\n  body\n;;\n\n"
        "[DELTA.session-1]\n  body\n;;\n\n"
        ";;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert _has_warning(report, "duplicate_delta_session_id")


def test_full_v3_spec_parses_and_validates() -> None:
    doc = Document.parse(_read("SPEC.clm"))
    report = validate_v3(doc)
    assert report.errors == [], f"SPEC.clm errors: {report.errors}"


def test_missing_decisions_live_sentinel_is_error() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n"
        ";;; trim.config: roll_call=10, dream_log=3, decisions_live=2\n"
        ";;; ---\n\n"
        "[STATE]\n"
        "  decisions.live (last 2 of 5 archived):\n"
        "    d3: keep me [session 30]\n"
        "    d4: keep me too [session 40]\n"
        "    d5: keep me also [session 50]\n"
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert any(
        e.kind == "sentinel_missing_in_trimmed_section"
        and e.details.get("section") == "STATE.decisions.live"
        for e in report.errors
    ), f"got: {report.errors}"


def test_decisions_live_sentinel_present_is_ok() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n"
        ";;; trim.config: roll_call=10, dream_log=3, decisions_live=2\n"
        ";;; ---\n\n"
        "[STATE]\n"
        "  decisions.live (last 2 of 5 archived):\n"
        "    ;; (oldest 3 live decisions offloaded to [DECISIONS.ARCHIVE] in sibling)\n"
        "    d4: keep me [session 40]\n"
        "    d5: keep me too [session 50]\n"
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert not any(
        e.kind == "sentinel_missing_in_trimmed_section"
        and e.details.get("section") == "STATE.decisions.live"
        for e in report.errors
    )


def test_delta_archive_section_is_not_session_id_validated() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n"
        "[STATE]\n  ;; empty\n;;\n\n"
        "[DELTA.ARCHIVE]\n"
        "  [DELTA.session-1]\n"
        "    ;; older delta archived inline\n"
        ";;\n\n"
        ";;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert not any(
        e.kind == "invalid_delta_session_id" and e.details.get("session_id") == "ARCHIVE"
        for e in report.errors
    )


def test_dreamed_inline_archive_artifact_validates() -> None:
    doc = Document.parse(_read("experiments/v3/dreamed.clm"))
    report = validate_v3(doc)
    assert report.errors == [], f"errors: {report.errors}"


def test_dreamed_sibling_50_trim_artifact_validates() -> None:
    doc = Document.parse(_read("experiments/v3/dreamed-sibling-50-trim.clm"))
    report = validate_v3(doc)
    assert report.errors == [], f"errors: {report.errors}"


def test_dreamed_sibling_200_trim_artifact_validates() -> None:
    doc = Document.parse(_read("experiments/v3/dreamed-sibling-200-trim.clm"))
    report = validate_v3(doc)
    assert report.errors == [], f"errors: {report.errors}"


def test_malformed_roll_call_entry_quarantined() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n"
        ";;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        '  CLd.Snt4.6 · 2026-04-07 · "a"\n'
        '  CLd.Ops4.6 · 2026-04-07 · "b"\n'
        "  this is junk that doesn't match the format\n"
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert not _has_error(report, "sentinel_missing_in_trimmed_section")
    assert _has_warning(report, "malformed_entry")


def test_filesystem_check_state_b_missing_archive_warns() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n"
        ";;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[STATE]\n  ;; empty\n;;\n\n"
        "[ROLL.CALL]\n"
        '  CLd.Snt4.6 · 2026-04-07 · "only one entry, no overflow"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3_with_filesystem(Document.parse(text), Path("/tmp"))
    assert report.errors == []
    assert _has_warning(report, "archive_file_not_yet_created_in_state_b")


def test_filesystem_check_state_c_missing_archive_errors() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n"
        ";;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        "  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n"
        '  CLd.Ops4.6 · 2026-04-07 · "b"\n'
        '  CLd.Snt4.5 · 2026-04-24 · "c"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3_with_filesystem(Document.parse(text), Path("/tmp"))
    assert _has_error(report, "archive_file_missing_in_state_c")


def test_archive_section_entries_are_validated() -> None:
    text = (
        ";;; CLM/3.0 — archive sibling\n;;; t.archive.clm\n;;; ---\n\n"
        "[ROLL.CALL.ARCHIVE]\n"
        '  CLd.X · 2026-01-01 · "valid line"\n'
        "  this is a malformed archive line with no separator\n"
        ";;\n\n;;; EOF | archive\n"
    )
    report = validate_v3(Document.parse(text))
    assert any(
        w.kind == "malformed_entry" and w.details.get("section") == "ROLL.CALL.ARCHIVE"
        for w in report.warnings
    )


def test_last_x_of_y_archived_form_triggers_sentinel_check() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n"
        ";;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[STATE]\n"
        "  decisions.live (last 8 of 23 archived):\n"
        + "".join(f"    d{i}: keep me [session {i*2}]\n" for i in range(16, 24))
        + ";;\n\n"
        ";;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert any(
        e.kind == "sentinel_missing_in_trimmed_section"
        and e.details.get("section") == "STATE.decisions.live"
        for e in report.errors
    ), f"got: {report.errors}"


def test_sentinel_after_kept_entries_is_not_accepted() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n"
        ";;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        '  CLd.Ops4.6 · 2026-04-07 · "b"\n'
        '  CLd.Snt4.5 · 2026-04-24 · "c"\n'
        '  CLd.Ops4.7 · 2026-04-25 · "d"\n'
        "  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n"
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3(Document.parse(text))
    assert _has_error(report, "sentinel_missing_in_trimmed_section")


def test_parser_permissive_validator_strict_for_delta_session_id() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n"
        "[STATE]\n  ;; empty\n;;\n\n"
        "[DELTA.session-X]\n  ;; X is uppercase, malformed session-id\n;;\n\n"
        ";;; EOF | CLM/3.0\n"
    )
    doc = Document.parse(text)
    report = validate_v3(doc)
    assert any(
        e.kind == "invalid_delta_session_id" and e.details.get("session_id") == "session-X"
        for e in report.errors
    )


def test_declared_offload_marks_state_c_for_filesystem_check() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n"
        ";;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[STATE]\n"
        "  decisions.live (last 8 of 23 archived):\n"
        + "".join(f"    d{i}: keep me [session {i*2}]\n" for i in range(16, 24))
        + ";;\n\n"
        ";;; EOF | CLM/3.0\n"
    )
    report = validate_v3_with_filesystem(Document.parse(text), Path("/tmp"))
    assert _has_error(report, "archive_file_missing_in_state_c")


def test_archive_path_pointing_to_directory_errors_in_state_c() -> None:
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        ";;; trim.mode: aggressive | archive.mode: sibling | archive.path: .\n"
        ";;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        "  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n"
        '  CLd.Ops4.6 · 2026-04-07 · "b"\n'
        '  CLd.Snt4.5 · 2026-04-24 · "c"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3_with_filesystem(Document.parse(text), Path("/tmp"))
    assert _has_error(report, "archive_file_missing_in_state_c")


def test_live_section_without_sentinel_errors_when_archive_exists(tmp_path: Path) -> None:
    archive_path = tmp_path / "x.archive.clm"
    archive_path.write_text(
        ";;; CLM/3.0 — archive\n;;; ---\n\n"
        "[ROLL.CALL.ARCHIVE]\n"
        '  CLd.X · 2026-01-01 · "first"\n'
        ";;\n\n;;; EOF | archive\n"
    )
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        f";;; trim.mode: aggressive | archive.mode: sibling | archive.path: {archive_path.name}\n"
        ";;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        '  CLd.Ops4.6 · 2026-04-07 · "only one entry visible"\n'
        '  CLd.Snt4.5 · 2026-04-24 · "another"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3_with_filesystem(Document.parse(text), tmp_path)
    assert any(
        e.kind == "sentinel_missing_in_trimmed_section" and e.details.get("section") == "ROLL.CALL"
        for e in report.errors
    ), f"got: {report.errors}"


def test_archive_doc_warnings_propagate_to_live_report(tmp_path: Path) -> None:
    archive_path = tmp_path / "x.archive.clm"
    archive_path.write_text(
        ";;; CLM/3.0 — archive\n;;; ---\n\n"
        "[ROLL.CALL.ARCHIVE]\n"
        '  CLd.X · 2026-01-01 · "valid"\n'
        "  bogus line missing the separator\n"
        ";;\n\n;;; EOF | archive\n"
    )
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        f";;; trim.mode: aggressive | archive.mode: sibling | archive.path: {archive_path.name}\n"
        ";;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        "  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n"
        '  CLd.Ops4.6 · 2026-04-07 · "recent"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3_with_filesystem(Document.parse(text), tmp_path)
    assert any(
        w.kind == "malformed_entry" and w.details.get("section") == "ROLL.CALL.ARCHIVE"
        for w in report.warnings
    )


def test_iso_date_rejects_non_ascii_digits() -> None:
    # Sonnet review I2: Python str.isdigit() accepts non-ASCII digits (Thai, Arabic-Indic).
    # Rust b.is_ascii_digit() and JS \d (no u flag) only accept ASCII.
    # Use the helper directly via imports to keep test surface tight.
    from clm.validate import _looks_like_iso_date  # type: ignore[attr-defined]

    assert _looks_like_iso_date("2026-04-25")
    assert not _looks_like_iso_date("\u0e50\u0e50\u0e50\u0e50-\u0e50\u0e51-\u0e50\u0e51")  # Thai digits
    assert not _looks_like_iso_date("\u0660\u0660\u0660\u0660-\u0660\u0661-\u0660\u0661")  # Arabic-Indic
    assert not _looks_like_iso_date("notadate12")


def test_archive_file_pointing_at_wrong_shape_errors_in_state_c(tmp_path: Path) -> None:
    stale_path = tmp_path / "stale.clm"
    stale_path.write_text(
        ";;; CLM/3.0 — not an archive\n;;; ---\n\n"
        "[META]\n  ;; nope\n;;\n\n"
        ";;; EOF | CLM/3.0\n"
    )
    text = (
        ";;; CLM/3.0 — test\n;;; test.clm\n"
        f";;; trim.mode: aggressive | archive.mode: sibling | archive.path: {stale_path.name}\n"
        ";;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n"
        ";;; ---\n\n"
        "[ROLL.CALL]\n"
        "  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n"
        '  CLd.Ops4.6 · 2026-04-07 · "b"\n'
        '  CLd.Snt4.5 · 2026-04-24 · "c"\n'
        ";;\n\n;;; EOF | CLM/3.0\n"
    )
    report = validate_v3_with_filesystem(Document.parse(text), tmp_path)
    assert _has_error(report, "archive_file_wrong_shape_in_state_c")
