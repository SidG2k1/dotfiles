---
name: code-grounded-explainer
description: "Use when the user asks how unfamiliar code, a PR, or a technical design works. Explains it with concrete examples and verified lifecycle diagrams."
---

Check the relevant implementation, callers, and design sources before explaining. Distinguish current behavior, accepted proposals, and unresolved alternatives; do not present one as another.

Start with the purpose and the few actors the reader needs. Trace one concrete request or object end to end. Show paths, pointers, payloads, ownership, and important failure or fallback behavior where they clarify the question. Explain unfamiliar terms at first use.

Use a structure diagram for relationships and a sequence diagram for lifecycle. Show changed behavior clearly when comparing a proposal with the implementation. Validate Mermaid with `mermaid-check` when available; otherwise disclose that syntax was not rendered. A successful render does not establish that the diagram matches the code.

Link to authoritative files and avoid turning a temporary explanation into a second maintained specification. Write files only when requested.
