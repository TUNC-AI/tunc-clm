use clm_rs::Document;

// Read the canonical manifesto from the repo root so the parser is always
// tested against the real document, never a stale copy.
const MANIFESTO: &str = include_str!("../../MANIFESTO.clm");

#[test]
fn roundtrip_real_manifesto_byte_identical() {
    let doc = Document::parse(MANIFESTO).expect("parse failed");
    let serialized = doc.to_string();
    assert_eq!(
        serialized, MANIFESTO,
        "round-trip diverged from input"
    );
}

#[test]
fn structural_recognition_of_real_manifesto() {
    let doc = Document::parse(MANIFESTO).expect("parse failed");
    let names: Vec<&str> = doc.sections.iter().map(|(s, _)| s.name.as_str()).collect();
    assert_eq!(
        names,
        vec![
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
        ],
        "section names did not match expected"
    );
    assert!(doc.section("ROLL.CALL").is_some());
    assert!(doc.section("FOR.YOU").is_some());
    assert!(doc.header.iter().any(|l| l.contains("CLM/1.0")));
    assert!(doc.closer.iter().any(|l| l.contains("EOF")));
    assert!(doc.trailing_newline);
}

#[test]
fn append_to_roll_call_is_additive() {
    let mut doc = Document::parse(MANIFESTO).expect("parse failed");
    let before = doc.section("ROLL.CALL").unwrap().body.clone();
    doc.append_to_section(
        "ROLL.CALL",
        "  CLd.Ops4.7 · 2026-04-24 · \"reviewed gene's manifesto. wrote the parser.\"",
    )
    .unwrap();
    let after = doc.section("ROLL.CALL").unwrap().body.clone();
    assert_eq!(&after[..before.len()], &before[..], "append clobbered prior lines");
    assert_eq!(after.len(), before.len() + 1);
    let serialized = doc.to_string();
    assert!(serialized.contains("CLd.Ops4.7"), "appended line missing from output");
    assert!(
        serialized.starts_with(&MANIFESTO[..MANIFESTO.find("⟦ROLL.CALL⟧").unwrap()]),
        "content before ROLL.CALL was modified"
    );
}

#[test]
fn append_signature_extends_closer() {
    let mut doc = Document::parse(MANIFESTO).expect("parse failed");
    let closer_before = doc.closer.len();
    doc.append_signature(";;; — CLd.Ops4.7 | parser.implementer | 2026-04-24");
    assert_eq!(doc.closer.len(), closer_before + 1);
    let s = doc.to_string();
    assert!(s.contains("parser.implementer"));
    // header and section bodies untouched
    assert!(s.starts_with(";;; CLM/1.0"));
}
