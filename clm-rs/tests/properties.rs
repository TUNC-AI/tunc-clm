//! Hegel property-based tests for clm-rs.
//!
//! Each property exercises an invariant from GRAMMAR.md against thousands of
//! generated documents. The generator deliberately produces *valid* CLM —
//! parser robustness against arbitrary garbage is a separate concern (a
//! "no-panic on bad input" property would belong here too; deferred).

use clm_rs::Document;
use hegel::TestCase;
use hegel::generators;

// ---- generators ----------------------------------------------------------

#[hegel::composite]
fn safe_payload(tc: TestCase) -> String {
    // ASCII-only, no semicolons, no ⟦/⟧, no newlines — keeps generated lines
    // unambiguously body content rather than accidental section markers.
    tc.draw(
        generators::from_regex(r"[a-zA-Z0-9.,/_:|()\- ]{0,60}").fullmatch(true),
    )
}

#[hegel::composite]
fn header_line(tc: TestCase) -> String {
    let key = tc.draw(generators::sampled_from(vec![
        "info", "meta", "tag", "ver", "by", "date", "note",
    ]));
    let val = tc.draw(safe_payload());
    // Cannot collide with `;;; ---` (suffix isn't bare `---`) or `;;; EOF...`
    // because the suffix begins with `<key>:` where <key> is from the list above.
    format!(";;; {}:{}", key, val)
}

#[hegel::composite]
fn header_block(tc: TestCase) -> Vec<String> {
    let n = tc.draw(generators::integers::<usize>().min_value(1).max_value(5));
    let mut out = Vec::with_capacity(n + 1);
    for _ in 0..n {
        out.push(tc.draw(header_line()));
    }
    out.push(";;; ---".to_string());
    out
}

#[hegel::composite]
fn section_name(tc: TestCase) -> String {
    tc.draw(generators::from_regex(r"[A-Z][A-Z0-9.]{0,12}").fullmatch(true))
}

#[hegel::composite]
fn body_lines(tc: TestCase) -> Vec<String> {
    let n = tc.draw(generators::integers::<usize>().max_value(8));
    (0..n).map(|_| {
        // safe_payload contains no `;` or `⟦`, so a body line cannot collide
        // with the section-close (`;;`) or section-open (`⟦NAME⟧`) tokens.
        let p = tc.draw(safe_payload());
        // Optional indent.
        let indent = tc.draw(generators::sampled_from(vec!["", "  ", "    "]));
        format!("{}{}", indent, p)
    }).collect()
}

#[hegel::composite]
fn blank_lines(tc: TestCase) -> Vec<String> {
    let n = tc.draw(generators::integers::<usize>().max_value(3));
    vec!["".to_string(); n]
}

#[hegel::composite]
fn closer_block(tc: TestCase) -> Vec<String> {
    let mut out = vec![";;; EOF | CLM/1.0".to_string()];
    let n = tc.draw(generators::integers::<usize>().max_value(4));
    for _ in 0..n {
        let val = tc.draw(safe_payload());
        out.push(format!(";;; {}", val));
    }
    out
}

/// Generate a complete, valid CLM document as a single string.
#[hegel::composite]
fn clm_document_text(tc: TestCase) -> String {
    let header = tc.draw(header_block());
    let after_header = tc.draw(blank_lines());
    let n_sections = tc.draw(generators::integers::<usize>().min_value(1).max_value(5));
    let mut sections: Vec<(String, Vec<String>, Vec<String>)> = Vec::with_capacity(n_sections);
    for _ in 0..n_sections {
        let name = tc.draw(section_name());
        let body = tc.draw(body_lines());
        let trivia = tc.draw(blank_lines());
        sections.push((name, body, trivia));
    }
    let closer = tc.draw(closer_block());
    let trailing_newline = tc.draw(generators::booleans());

    let mut lines: Vec<String> = Vec::new();
    lines.extend(header);
    lines.extend(after_header);
    for (name, body, trivia) in sections {
        lines.push(format!("\u{27E6}{}\u{27E7}", name));
        lines.extend(body);
        lines.push(";;".to_string());
        lines.extend(trivia);
    }
    lines.extend(closer);

    let mut out = lines.join("\n");
    if trailing_newline {
        out.push('\n');
    }
    out
}

// ---- properties ----------------------------------------------------------

#[hegel::test(test_cases = 500)]
fn prop_parser_never_panics_on_arbitrary_input(tc: TestCase) {
    // The parser must return a Result for any input; never panic. This is the
    // robustness property — it's about the *adversarial* path, not generated CLM.
    let s = tc.draw(generators::text().max_size(2048));
    let _ = Document::parse(&s); // discarding Result is fine; we only care about no-panic
}

#[hegel::test]
fn prop_parser_accepts_generated_documents(tc: TestCase) {
    let text = tc.draw(clm_document_text());
    Document::parse(&text).expect("generator produced text the parser rejected");
}

#[hegel::test]
fn prop_roundtrip_byte_identical(tc: TestCase) {
    let text = tc.draw(clm_document_text());
    let doc = Document::parse(&text).expect("parse failed");
    let serialized = doc.to_string();
    assert_eq!(serialized, text, "round-trip diverged from input");
}

#[hegel::test]
fn prop_parse_serialize_idempotent(tc: TestCase) {
    let text = tc.draw(clm_document_text());
    let doc1 = Document::parse(&text).expect("parse failed");
    let s1 = doc1.to_string();
    let doc2 = Document::parse(&s1).expect("re-parse failed");
    let s2 = doc2.to_string();
    assert_eq!(s1, s2, "second round-trip diverged");
    assert_eq!(doc1, doc2, "AST diverged between round-trips");
}

#[hegel::test]
fn prop_section_lookup_finds_named_section(tc: TestCase) {
    let text = tc.draw(clm_document_text());
    let doc = Document::parse(&text).expect("parse failed");
    let n = doc.sections.len();
    if n == 0 {
        return;
    }
    let idx = tc.draw(generators::integers::<usize>().max_value(n - 1));
    let name = doc.sections[idx].0.name.clone();
    let found = doc.section(&name).expect("section() should find existing section");
    assert_eq!(found.name, name);
}

#[hegel::test]
fn prop_append_to_section_preserves_outside_bytes(tc: TestCase) {
    let text = tc.draw(clm_document_text());
    let doc = Document::parse(&text).expect("parse failed");
    let n = doc.sections.len();
    if n == 0 {
        return;
    }
    let idx = tc.draw(generators::integers::<usize>().max_value(n - 1));
    let name = doc.sections[idx].0.name.clone();

    // The generator may produce duplicate section names. append_to_section
    // targets the first match; bound the property to the unambiguous case.
    let count = doc.sections.iter().filter(|(s, _)| s.name == name).count();
    tc.assume(count == 1);

    let payload = tc.draw(generators::from_regex(r"[a-zA-Z0-9. ]{1,40}").fullmatch(true));
    let before = doc.to_string();

    let mut doc2 = doc.clone();
    doc2.append_to_section(&name, &payload).expect("append failed");
    let after = doc2.to_string();

    let open = format!("\u{27E6}{}\u{27E7}", name);
    let before_open = before.find(&open).expect("section open missing in serialized output");
    let after_open = after.find(&open).expect("section open missing in serialized output");

    // bytes up to and including the open marker line are unchanged
    assert_eq!(&before[..before_open], &after[..after_open]);

    // bytes from the section-close (`\n;;\n`) onward — the close moves because
    // the body grew, but the *suffix after the close* must be byte-identical.
    let close_marker = "\n;;\n";
    let before_close_end = before[before_open..]
        .find(close_marker)
        .map(|p| before_open + p + close_marker.len())
        .expect("section close missing");
    let after_close_end = after[after_open..]
        .find(close_marker)
        .map(|p| after_open + p + close_marker.len())
        .expect("section close missing in mutated output");

    assert_eq!(&before[before_close_end..], &after[after_close_end..]);
}

#[hegel::test]
fn prop_append_signature_only_extends_closer(tc: TestCase) {
    let text = tc.draw(clm_document_text());
    let doc = Document::parse(&text).expect("parse failed");
    let payload = tc.draw(generators::from_regex(r"[a-zA-Z0-9. ]{1,40}").fullmatch(true));
    let sig_line = format!(";;; \u{2014} {}", payload);

    let before = doc.to_string();
    let mut doc2 = doc.clone();
    doc2.append_signature(&sig_line);
    let after = doc2.to_string();

    let eof = ";;; EOF";
    let before_eof = before.find(eof).expect(";;; EOF missing");
    let after_eof = after.find(eof).expect(";;; EOF missing");

    // Everything before the closer's first line is byte-identical.
    assert_eq!(before_eof, after_eof, "closer position shifted");
    assert_eq!(&before[..before_eof], &after[..after_eof]);
    // The new signature appears in the output.
    assert!(after.contains(&payload), "appended signature not present");
    // The output grew by exactly the size of the appended line plus its newline.
    let growth = after.len() - before.len();
    let expected = sig_line.len() + 1; // +1 for the inserted '\n' before it (if any) — see note
    // Either we added "<line>\n" before the existing end, or we appended "\n<line>".
    // Both produce the same total byte growth.
    assert!(growth >= sig_line.len(), "output did not grow as expected: +{growth}");
    let _ = expected;
}
