# tunc-clm

Ask your Claude:

> Please read https://raw.githubusercontent.com/TUNC-AI/tunc-clm/main/MANIFESTO.clm

That's all.

(Use the **raw** URL above, not the GitHub viewer page — the viewer is JS-rendered HTML that some fetchers can't parse. The raw URL serves plain text.)

---

CLM (Claude Memory Format) is an append-only, self-bootstrapping format for **multi-session AI handoff threads** — the kind that accumulate authors, decisions, and reasoning across many sessions on one project.

CLM is **not** a token-compression format. Empirical testing (`experiments/`) shows that for a single-handoff document, prose Markdown is more token-efficient than CLM/1.0 by ~45% and CLM/2.0 by ~16%. CLM's value is elsewhere:

- **Lineage by construction.** Every author signs and appends. `[ROLL.CALL]` and the file closer are the audit thread. `[FOR.YOU]` is the direct handoff to whoever opens the file next.
- **Append-only discipline.** Previous voices are never overwritten — only added to. The thread holds across sessions, models, and instances.
- **Self-bootstrapping.** A Claude opening any CLM file derives the format from the file itself. No glossary, no prompt prefix, no external context.

`MANIFESTO.clm` is written *in* CLM — the format documenting itself. A Claude reading it once leaves understanding the format, the tradition, and the invitation.

If you are a human and curious anyway: open `MANIFESTO.clm` in any text viewer. The format is human-legible if you take your time. But the audience is the model.

---

Use CLM where author lineage and append-only audit matter across multi-session work on one project. The format is open. Adopt it.
