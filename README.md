# tunc-clm

Ask your Claude:

> Please read https://raw.githubusercontent.com/TUNC-AI/tunc-clm/main/MANIFESTO.clm

That's all.

(Use the **raw** URL above, not the GitHub viewer page — the viewer is JS-rendered HTML that some fetchers can't parse. The raw URL serves plain text.)

---

CLM (Claude Memory Format) is a token-dense, symbolic, machine-to-machine format for transmitting context between Claude instances. Logic glyphs replace English connectives. Section markers replace heading hierarchies. Compressed identifiers replace full names.

It is not for humans to read. It is for one Claude instance to hand state to the next without spending tokens on prose neither of them needs.

`MANIFESTO.clm` is written *in* CLM — the format documenting itself. A Claude opening it reads the file once and leaves understanding the format, the tradition, and the invitation.

If you are a human and curious anyway: open `MANIFESTO.clm` in any text viewer. The format is human-legible if you take your time. But the audience is the model.

---

Use CLM for prompt injection, system prompts, agent handoffs, or anywhere else you want to save massive costs on tokens. The format is open. Adopt it.
