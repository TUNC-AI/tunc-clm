//! clm-rs — coarse-grained parser for the Claude Memory Format.
//!
//! Supports both CLM/1.0 (Unicode brackets `⟦NAME⟧`) and CLM/2.x+/3.0
//! (ASCII brackets `[NAME]`). The contract is round-trip:
//! `serialize(parse(D)) == D` byte-for-byte for any document accepted by
//! the grammar.
//!
//! v3.0 trim-aware validation lives in [`validate`].

pub mod validate;

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Document {
    pub header: Vec<String>,
    pub trivia_after_header: Vec<String>,
    pub sections: Vec<(Section, Vec<String>)>,
    pub closer: Vec<String>,
    pub trailing_newline: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Section {
    pub name: String,
    pub open_line: String,
    pub body: Vec<String>,
    pub close_line: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParseError {
    MissingHeader,
    MissingHeaderTerminator,
    MissingCloser,
    UnclosedSection { name: String, line: usize },
    UnexpectedTopLevelLine { line: usize, content: String },
    SectionInsideSection { line: usize },
    ContentAfterCloser { line: usize },
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ParseError::MissingHeader => write!(
                f,
                "missing file header (expected lines starting with ';;;')"
            ),
            ParseError::MissingHeaderTerminator => {
                write!(f, "missing header terminator (expected ';;; ---')")
            }
            ParseError::MissingCloser => {
                write!(f, "missing file closer (expected ';;; EOF ...')")
            }
            ParseError::UnclosedSection { name, line } => write!(
                f,
                "section \u{27E6}{name}\u{27E7} opened at line {line} was never closed (';;')"
            ),
            ParseError::UnexpectedTopLevelLine { line, content } => write!(
                f,
                "unexpected line at top level (line {line}): {content:?}"
            ),
            ParseError::SectionInsideSection { line } => {
                write!(f, "nested section opens are not allowed (line {line})")
            }
            ParseError::ContentAfterCloser { line } => {
                write!(f, "unexpected content after file closer (line {line})")
            }
        }
    }
}

impl std::error::Error for ParseError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MutationError {
    NoSuchSection(String),
}

impl fmt::Display for MutationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            MutationError::NoSuchSection(n) => {
                write!(f, "no such section: \u{27E6}{n}\u{27E7}")
            }
        }
    }
}

impl std::error::Error for MutationError {}

impl Document {
    pub fn parse(input: &str) -> Result<Self, ParseError> {
        let trailing_newline = input.ends_with('\n');
        let body = if trailing_newline {
            &input[..input.len() - 1]
        } else {
            input
        };
        let lines: Vec<&str> = if body.is_empty() {
            Vec::new()
        } else {
            body.split('\n').collect()
        };

        let mut idx = 0usize;

        // ---- header ----
        if idx >= lines.len() || !is_triple_semi(lines[idx]) {
            return Err(ParseError::MissingHeader);
        }
        let mut header = Vec::new();
        let mut found_terminator = false;
        while idx < lines.len() && is_triple_semi(lines[idx]) {
            header.push(lines[idx].to_string());
            if is_header_terminator(lines[idx]) {
                idx += 1;
                found_terminator = true;
                break;
            }
            idx += 1;
        }
        if !found_terminator {
            return Err(ParseError::MissingHeaderTerminator);
        }

        // ---- trivia after header ----
        let mut trivia_after_header = Vec::new();
        while idx < lines.len() && is_blank(lines[idx]) {
            trivia_after_header.push(lines[idx].to_string());
            idx += 1;
        }

        // ---- sections ----
        let mut sections: Vec<(Section, Vec<String>)> = Vec::new();
        loop {
            if idx >= lines.len() {
                return Err(ParseError::MissingCloser);
            }
            if is_closer_start(lines[idx]) {
                break;
            }
            let open_line = lines[idx].to_string();
            let name = match parse_section_open(&open_line) {
                Some(n) => n,
                None => {
                    return Err(ParseError::UnexpectedTopLevelLine {
                        line: idx + 1,
                        content: open_line,
                    });
                }
            };
            let open_line_idx = idx;
            idx += 1;

            let mut body_lines = Vec::new();
            let mut close_line: Option<String> = None;
            while idx < lines.len() {
                if is_section_close(lines[idx]) {
                    close_line = Some(lines[idx].to_string());
                    idx += 1;
                    break;
                }
                if parse_section_open(lines[idx]).is_some() {
                    return Err(ParseError::SectionInsideSection { line: idx + 1 });
                }
                body_lines.push(lines[idx].to_string());
                idx += 1;
            }
            let close_line = close_line.ok_or(ParseError::UnclosedSection {
                name: name.clone(),
                line: open_line_idx + 1,
            })?;

            let mut trivia = Vec::new();
            while idx < lines.len() && is_blank(lines[idx]) {
                trivia.push(lines[idx].to_string());
                idx += 1;
            }

            sections.push((
                Section {
                    name,
                    open_line,
                    body: body_lines,
                    close_line,
                },
                trivia,
            ));
        }

        // ---- closer ----
        let mut closer = Vec::new();
        while idx < lines.len() {
            if !is_triple_semi(lines[idx]) {
                return Err(ParseError::ContentAfterCloser { line: idx + 1 });
            }
            closer.push(lines[idx].to_string());
            idx += 1;
        }
        if closer.is_empty() || !is_closer_start(&closer[0]) {
            return Err(ParseError::MissingCloser);
        }

        Ok(Document {
            header,
            trivia_after_header,
            sections,
            closer,
            trailing_newline,
        })
    }

    pub fn section(&self, name: &str) -> Option<&Section> {
        self.sections
            .iter()
            .find(|(s, _)| s.name == name)
            .map(|(s, _)| s)
    }

    pub fn append_to_section(&mut self, name: &str, text: &str) -> Result<(), MutationError> {
        let entry = self
            .sections
            .iter_mut()
            .find(|(s, _)| s.name == name)
            .ok_or_else(|| MutationError::NoSuchSection(name.to_string()))?;
        for line in text.split('\n') {
            entry.0.body.push(line.to_string());
        }
        Ok(())
    }

    pub fn append_signature(&mut self, line: impl Into<String>) {
        self.closer.push(line.into());
    }
}

impl fmt::Display for Document {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for line in &self.header {
            f.write_str(line)?;
            f.write_str("\n")?;
        }
        for line in &self.trivia_after_header {
            f.write_str(line)?;
            f.write_str("\n")?;
        }
        for (section, trivia) in &self.sections {
            f.write_str(&section.open_line)?;
            f.write_str("\n")?;
            for line in &section.body {
                f.write_str(line)?;
                f.write_str("\n")?;
            }
            f.write_str(&section.close_line)?;
            f.write_str("\n")?;
            for line in trivia {
                f.write_str(line)?;
                f.write_str("\n")?;
            }
        }
        let last = self.closer.len().saturating_sub(1);
        for (i, line) in self.closer.iter().enumerate() {
            f.write_str(line)?;
            if i < last || self.trailing_newline {
                f.write_str("\n")?;
            }
        }
        Ok(())
    }
}

// ---- line classifiers ----

fn is_triple_semi(line: &str) -> bool {
    line.starts_with(";;;")
}

fn is_header_terminator(line: &str) -> bool {
    match line.strip_prefix(";;;") {
        Some(s) => s.trim() == "---",
        None => false,
    }
}

fn is_closer_start(line: &str) -> bool {
    let Some(after) = line.strip_prefix(";;;") else {
        return false;
    };
    let trimmed = after.trim_start();
    if !trimmed.starts_with("EOF") {
        return false;
    }
    let rest = &trimmed[3..];
    rest.is_empty() || !rest.as_bytes()[0].is_ascii_alphanumeric()
}

fn is_blank(line: &str) -> bool {
    line.chars().all(char::is_whitespace)
}

fn is_section_close(line: &str) -> bool {
    line.trim_end() == ";;"
}

const SEC_OPEN: &str = "\u{27E6}"; // ⟦
const SEC_CLOSE: &str = "\u{27E7}"; // ⟧

/// Recognize both Unicode (`⟦NAME⟧`, CLM/1.0) and ASCII (`[NAME]`, CLM/2.x+/3.0)
/// section opens. Returns the inner name on success.
fn parse_section_open(line: &str) -> Option<String> {
    let trimmed = line.trim_end();

    // CLM/1.0: Unicode brackets
    if let Some(inner) = trimmed
        .strip_prefix(SEC_OPEN)
        .and_then(|s| s.strip_suffix(SEC_CLOSE))
    {
        return validate_section_name(inner);
    }

    // CLM/2.x+ / 3.0: ASCII brackets
    if let Some(inner) = trimmed
        .strip_prefix('[')
        .and_then(|s| s.strip_suffix(']'))
    {
        return validate_section_name(inner);
    }

    None
}

/// Section names follow two patterns at the parser level:
///   - Plain: `[A-Z][A-Z0-9.]*` (e.g. STATE, ROLL.CALL, MODEL.FAMILIES)
///   - DELTA.<anything-that-looks-like-an-identifier-suffix>: parser is permissive here
///     so malformed session-ids reach `validate_v3` (which emits InvalidDeltaSessionId)
///     instead of dying with `UnexpectedTopLevelLine` at parse time. Spec-strict
///     session-id grammar `[a-z0-9][a-z0-9._-]*` is enforced by the validator, not the parser.
///
/// Plain-section grammar stays strict: lowercase / underscores / dashes in non-DELTA
/// names would let `[State]` slip past the parser and bypass validator name checks.
fn validate_section_name(inner: &str) -> Option<String> {
    if inner.is_empty() {
        return None;
    }
    // Permissive parse for DELTA.<suffix> — defer strict session-id check to validator.
    if let Some(suffix) = inner.strip_prefix("DELTA.") {
        if suffix.is_empty() {
            return None;
        }
        let valid_chars = suffix.chars().all(|c| {
            c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-'
        });
        if !valid_chars {
            return None;
        }
        return Some(inner.to_string());
    }
    // Plain section name: strict.
    let mut chars = inner.chars();
    let first = chars.next()?;
    if !first.is_ascii_uppercase() {
        return None;
    }
    if !chars.all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == '.') {
        return None;
    }
    Some(inner.to_string())
}
