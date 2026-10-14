---
name: verification-before-completion
description: Check evidence before claiming work is complete, fixed, or passing, or before committing or opening a PR.
---

# Verification Before Completion

Support each completion claim with evidence for the current revision or working tree.

1. Identify what would establish the claim: relevant tests, a build, observed behavior, an inspected diff, or a requirements check.
2. Inspect the actual command, result, exit status, and scope of any existing verification. A worker's summary alone is insufficient.
3. Run missing checks and rerun affected checks after relevant code or environment changes, unresolved failures, or newly identified risks. Reuse inspected results when they still cover the current state.
4. Compare the result with the requested outcome. Passing tests alone do not establish that every requirement is met.
5. Report what was checked and any limitations. Do not call a failure, an unavailable check, or unverified behavior passing.

Use the narrowest meaningful checks for the change, plus repository-required checks. For prose or configuration, inspect the requested content and use applicable syntax, link, or installation checks. Add tests only for a concrete regression or required behavior.

When claiming a regression test detects the original bug, establish that it fails without the fix and passes with it. Do not repeat that proof for each assertion.

For delegated work, inspect the complete diff and the worker's verification evidence before presenting it. Rerun checks when integration changes or incomplete evidence justify it.

This skill applies to claims about completed work. Delegating a task, continuing authorized work, or reporting progress does not itself require another verification run.
