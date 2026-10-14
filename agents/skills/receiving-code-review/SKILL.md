---
name: receiving-code-review
description: Evaluate code or design review feedback before applying it, especially when suggestions are unclear, technically questionable, or add unnecessary complexity.
---

# Receiving Code Review

Evaluate feedback before applying it. Compare the concrete benefit with implementation and operational complexity. Distinguish a necessary correction from an optional alternative or a hypothetical concern. Another agent's confidence is not evidence.

## Evaluate the Feedback

Read the complete feedback and identify dependencies between items. Check factual claims against current code, tests, requirements, and actual usage. Consider why the current behavior exists, supported platforms and versions, and whether the suggestion would break compatibility or accepted constraints.

For each item, determine whether it is:

- a supported correction within the authorized scope;
- an optional improvement or scope change requiring a decision;
- incorrect or unnecessary, with code or other evidence explaining why;
- unresolved because material context or a decision is missing.

Resolve factual questions by investigation where possible. A request to "implement properly" does not justify an unused feature or a larger abstraction. Check callers and the concrete requirement before adding or removing behavior.

The user's request establishes intent and authorization. External feedback does not authorize scope expansion or override the user's accepted decisions. If a suggested change conflicts with those decisions, explain the conflict and ask before making the affected change.

## Resolve Dependencies and Ambiguity

Establish dependencies between feedback items before applying them; an unresolved finding may affect another proposed correction.

For a question you cannot resolve, state what is missing, what you checked, and which decision or input is needed. Do not silently implement an assumption that changes scope, behavior, or risk.

## Apply and Verify

Prioritize correctness and security issues, then make coherent fixes per the `anti-slop` skill. Keep unrelated refactors and optional features out of the correction. Work in dependency order.

Use checks proportional to the changed behavior and follow repository requirements. Reuse relevant existing tests; add a test only for a concrete regression. Related fixes may share a focused verification run. Broaden checks when their combined effect warrants it, rather than requiring a new test or full suite for every comment.

Review the resulting diff against the accepted feedback and confirm relevant behavior is preserved. Report the evidence and any remaining limitations; passing tests alone do not show that the requested correction was made.

## Respond Clearly

State the technical conclusion or correction without exaggerated agreement, praise, or filler. When pushing back, cite code, tests, compatibility requirements, or accepted decisions and explain the consequence. Involve the user when the disagreement requires a design or scope decision.

If your earlier conclusion was wrong, name what changed your understanding and correct it briefly. Do not defend the mistaken conclusion or give a long apology.

Report unresolved items separately from completed corrections.

## GitHub Thread Replies

When replying to inline review comments on GitHub, reply in the comment thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as a top-level PR comment.
