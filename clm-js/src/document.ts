/**
 * Coarse-grained parser for the Claude Memory Format.
 *
 * Supports both CLM/1.0 (Unicode brackets `⟦NAME⟧`) and CLM/2.x+/3.0
 * (ASCII brackets `[NAME]`). The contract is round-trip:
 * `Document.parse(text).toString() === text` byte-for-byte for any document
 * accepted by the grammar.
 *
 * v3.0 trim-aware validation lives in `./validate.ts`.
 */

const SEC_OPEN = "\u27E6"; // ⟦
const SEC_CLOSE = "\u27E7"; // ⟧

export class ParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ParseError";
  }
}

export class MutationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MutationError";
  }
}

export interface Section {
  name: string;
  openLine: string;
  body: string[];
  closeLine: string;
}

export class Document {
  header: string[] = [];
  triviaAfterHeader: string[] = [];
  /** Each section paired with the trivia (typically blank lines) that follows it. */
  sections: Array<{ section: Section; trivia: string[] }> = [];
  closer: string[] = [];
  trailingNewline = true;

  // ---- parsing ----

  static parse(text: string): Document {
    const doc = new Document();
    doc.trailingNewline = text.endsWith("\n");
    const body = doc.trailingNewline ? text.slice(0, -1) : text;
    const lines = body.length === 0 ? [] : body.split("\n");

    let idx = 0;

    // Header
    if (idx >= lines.length || !isTripleSemi(lines[idx]!)) {
      throw new ParseError("missing file header (expected lines starting with ';;;')");
    }
    let foundTerminator = false;
    while (idx < lines.length && isTripleSemi(lines[idx]!)) {
      doc.header.push(lines[idx]!);
      if (isHeaderTerminator(lines[idx]!)) {
        idx++;
        foundTerminator = true;
        break;
      }
      idx++;
    }
    if (!foundTerminator) {
      throw new ParseError("missing header terminator (expected ';;; ---')");
    }

    // Trivia after header (blank lines)
    while (idx < lines.length && isBlank(lines[idx]!)) {
      doc.triviaAfterHeader.push(lines[idx]!);
      idx++;
    }

    // Sections
    while (true) {
      if (idx >= lines.length) {
        throw new ParseError("missing file closer (expected ';;; EOF ...')");
      }
      if (isCloserStart(lines[idx]!)) {
        break;
      }
      const openLine = lines[idx]!;
      const name = parseSectionOpen(openLine);
      if (name === null) {
        throw new ParseError(
          `unexpected line at top level (line ${idx + 1}): ${JSON.stringify(openLine)}`
        );
      }
      const openLineIdx = idx;
      idx++;

      const sectionBody: string[] = [];
      let closeLine: string | null = null;
      while (idx < lines.length) {
        if (isSectionClose(lines[idx]!)) {
          closeLine = lines[idx]!;
          idx++;
          break;
        }
        if (parseSectionOpen(lines[idx]!) !== null) {
          throw new ParseError(`nested section opens are not allowed (line ${idx + 1})`);
        }
        sectionBody.push(lines[idx]!);
        idx++;
      }
      if (closeLine === null) {
        throw new ParseError(
          `section [${name}] opened at line ${openLineIdx + 1} was never closed (';;')`
        );
      }

      const trivia: string[] = [];
      while (idx < lines.length && isBlank(lines[idx]!)) {
        trivia.push(lines[idx]!);
        idx++;
      }

      doc.sections.push({
        section: { name, openLine, body: sectionBody, closeLine },
        trivia,
      });
    }

    // Closer
    while (idx < lines.length) {
      if (!isTripleSemi(lines[idx]!)) {
        throw new ParseError(`unexpected content after file closer (line ${idx + 1})`);
      }
      doc.closer.push(lines[idx]!);
      idx++;
    }
    if (doc.closer.length === 0 || !isCloserStart(doc.closer[0]!)) {
      throw new ParseError("missing file closer (expected ';;; EOF ...')");
    }

    return doc;
  }

  // ---- accessors ----

  section(name: string): Section | undefined {
    const found = this.sections.find((entry) => entry.section.name === name);
    return found?.section;
  }

  // ---- mutation ----

  appendToSection(name: string, text: string): void {
    const entry = this.sections.find((e) => e.section.name === name);
    if (!entry) throw new MutationError(`no such section: [${name}]`);
    for (const line of text.split("\n")) {
      entry.section.body.push(line);
    }
  }

  appendSignature(line: string): void {
    this.closer.push(line);
  }

  // ---- serialization ----

  toString(): string {
    const out: string[] = [];
    for (const line of this.header) {
      out.push(line, "\n");
    }
    for (const line of this.triviaAfterHeader) {
      out.push(line, "\n");
    }
    for (const { section, trivia } of this.sections) {
      out.push(section.openLine, "\n");
      for (const bodyLine of section.body) {
        out.push(bodyLine, "\n");
      }
      out.push(section.closeLine, "\n");
      for (const line of trivia) {
        out.push(line, "\n");
      }
    }
    const last = this.closer.length - 1;
    for (let i = 0; i < this.closer.length; i++) {
      out.push(this.closer[i]!);
      if (i < last || this.trailingNewline) {
        out.push("\n");
      }
    }
    return out.join("");
  }
}

// ---- line classifiers ----

function isTripleSemi(line: string): boolean {
  return line.startsWith(";;;");
}

function isHeaderTerminator(line: string): boolean {
  if (!line.startsWith(";;;")) return false;
  return line.slice(3).trim() === "---";
}

function isCloserStart(line: string): boolean {
  if (!line.startsWith(";;;")) return false;
  // Unicode-equivalent whitespace strip — Rust uses .trim_start() and Python .lstrip(),
  // both of which handle full Unicode whitespace. Limiting to [\t ] would reject docs
  // with NBSP (U+00A0) or other Unicode whitespace that the other implementations accept.
  const after = line.slice(3).replace(/^\s+/, "");
  if (!after.startsWith("EOF")) return false;
  const rest = after.slice(3);
  if (rest.length === 0) return true;
  const c = rest.charCodeAt(0);
  // Not ASCII alphanumeric.
  return !((c >= 0x30 && c <= 0x39) || (c >= 0x41 && c <= 0x5a) || (c >= 0x61 && c <= 0x7a));
}

function isBlank(line: string): boolean {
  if (line.length === 0) return true;
  return /^\s*$/.test(line);
}

function isSectionClose(line: string): boolean {
  return line.replace(/\s+$/, "") === ";;";
}

function parseSectionOpen(line: string): string | null {
  const trimmed = line.replace(/\s+$/, "");
  // CLM/1.0: Unicode brackets
  if (trimmed.startsWith(SEC_OPEN) && trimmed.endsWith(SEC_CLOSE)) {
    return validateSectionName(trimmed.slice(SEC_OPEN.length, -SEC_CLOSE.length));
  }
  // CLM/2.x+/3.0: ASCII brackets
  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    return validateSectionName(trimmed.slice(1, -1));
  }
  return null;
}

/**
 * Permissive parser-level grammar; strict semantics enforced in `./validate.ts`.
 *
 * Plain section names: `[A-Z][A-Z0-9.]*` (uppercase only).
 * `DELTA.<suffix>`: parser accepts any identifier-shaped suffix; validator enforces
 * the spec session-id grammar so malformed names surface as InvalidDeltaSessionId.
 */
function validateSectionName(inner: string): string | null {
  if (inner.length === 0) return null;
  // Permissive parse for DELTA.<suffix>.
  if (inner.startsWith("DELTA.")) {
    const suffix = inner.slice("DELTA.".length);
    if (suffix.length === 0) return null;
    if (!/^[A-Za-z0-9._-]+$/.test(suffix)) return null;
    return inner;
  }
  // Plain section name: strict.
  if (!/^[A-Z][A-Z0-9.]*$/.test(inner)) return null;
  return inner;
}
