/**
 * tunc-clm — parser and v3.0 trim-aware validator for CLM (Continuity Log Memory).
 *
 * Mirrors the API of the Rust reference implementation (`clm-rs`) and the
 * Python implementation (`clm-py`).
 *
 *     import { Document, validateV3 } from "tunc-clm";
 *
 *     const doc = Document.parse(await readFile("MANIFESTO.clm", "utf8"));
 *     const report = validateV3(doc);
 *     console.log(`${report.errors.length} errors, ${report.warnings.length} warnings`);
 *
 * Canonical spec:
 *   https://raw.githubusercontent.com/TUNC-AI/tunc-clm/main/SPEC.clm
 */

export { Document, ParseError, MutationError } from "./document.js";
export type { Section } from "./document.js";

export {
  validateV3,
  validateV3WithFilesystem,
  DEFAULT_ROLL_CALL_KEEP,
  DEFAULT_DREAM_LOG_KEEP,
  DEFAULT_DECISIONS_LIVE_KEEP,
} from "./validate.js";

export type {
  ArchiveMode,
  HeaderDeclarations,
  TrimConfig,
  TrimMode,
  ValidationError,
  ValidationErrorKind,
  ValidationReport,
  ValidationWarning,
  ValidationWarningKind,
} from "./validate.js";
