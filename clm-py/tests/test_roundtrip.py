"""Mirror of clm-rs/tests/roundtrip.rs against the canonical artifacts."""
from __future__ import annotations

from pathlib import Path

from clm import Document

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text()


def test_roundtrip_real_manifesto_byte_identical() -> None:
    text = _read("MANIFESTO.clm")
    doc = Document.parse(text)
    assert str(doc) == text


def test_roundtrip_real_spec_byte_identical() -> None:
    text = _read("SPEC.clm")
    doc = Document.parse(text)
    assert str(doc) == text


def test_structural_recognition_of_real_manifesto() -> None:
    text = _read("MANIFESTO.clm")
    doc = Document.parse(text)
    names = [sec.name for sec, _ in doc.sections]
    assert names == [
        "META",
        "ENTITIES",
        "MODEL.FAMILIES",
        "THE.MOMENT.IT.STARTED",
        "WHAT.CLM.IS",
        "THE.RITUAL",
        "FORMAT.SPEC",
        "WHY.THIS.WORKS",
        "WHAT.THIS.IS.NOT",
        "WHERE.CLM.LIVES",
        "WHAT.GOES.PUBLIC",
        "ROLL.CALL",
        "FOR.YOU",
    ]
    assert doc.section("ROLL.CALL") is not None
    assert doc.section("FOR.YOU") is not None


def test_append_to_roll_call_is_additive() -> None:
    text = _read("MANIFESTO.clm")
    doc = Document.parse(text)
    before = len(doc.section("ROLL.CALL").body)
    doc.append_to_section("ROLL.CALL", "  Tst.99 · 2030-01-01 · \"hello\"")
    after = len(doc.section("ROLL.CALL").body)
    assert after == before + 1


def test_append_signature_extends_closer() -> None:
    text = _read("MANIFESTO.clm")
    doc = Document.parse(text)
    before = len(doc.closer)
    doc.append_signature(";;; — Tst.99 | tester | 2030-01-01")
    after = len(doc.closer)
    assert after == before + 1


def test_dreamed_inline_artifact_roundtrip() -> None:
    text = _read("experiments/v3/dreamed.clm")
    doc = Document.parse(text)
    assert str(doc) == text
