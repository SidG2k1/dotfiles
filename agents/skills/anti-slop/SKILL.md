---
name: anti-slop
description: Use when implementing or reviewing code or docs where agent-generated changes risk overengineering, unnecessary abstractions, excessive tests, diff bloat, dependency creep, scope creep, doc rot, or non-idiomatic Python, Go, Rust, frontend, or Markdown output.
---

# Anti-Slop Coding

## Principle

Make the smallest correct change that fits the codebase. Minimize code, files, concepts, dependencies, tests, and churn — not understanding, correctness, or necessary verification.

## Before coding

Understand the requested behavior and trace the path being changed. Then stop at the first option that works:

1. **Do nothing / delete** — new code is unnecessary.
2. **Reuse** — the codebase already has the behavior or pattern.
3. **Stdlib** — the language already provides it.
4. **Native** — the browser, HTML/CSS, database, OS, or framework provides it.
5. **Existing dependency** — an installed package solves it cleanly.
6. **Direct implementation** — write the minimum local code for the current requirement.

Understand first; do not turn this ladder into a research project.

## Scope and design

- Change only what the requested behavior requires. No adjacent cleanup or opportunistic refactors.
- Prefer the fewest files and concepts that preserve clear ownership.
- No interface, factory, base class, wrapper, service, repository, config layer, or generic framework for one current implementation.
- No speculative flexibility, extension points, fallbacks, or configuration for hypothetical requirements.
- No new dependency when built-ins, existing dependencies, or small local code suffice.
- Preserve repository conventions. Comments explain non-obvious **why**, not obvious **what**.
- Duplication can be cheaper than the wrong abstraction. Extract only when a stable concept exists.

If a small request unexpectedly produces many files, a dependency, an abstraction layer, or a large diff, reconsider the approach. Large is a warning signal, not automatically wrong.

## Tests and verification

Tests protect behavior; test count and coverage percentage are not goals.

Before adding a test, name the concrete regression it would catch. If none can be named, do not add it. Avoid tests that duplicate existing scenarios, cover trivial pass-through/type guarantees, assert private implementation details, overmock internals, or require new scaffolding for one small case.

Absence-confirmation tests are almost always slop. Do not add tests that merely assert removed files, symbols, names, commands, or implementation text stay absent; remove such assertions when reviewing existing tests. Keep negative assertions only when they protect a concrete behavior or safety requirement, such as rejecting unauthorized access, preventing secret exposure, or preserving files outside a deployment's ownership.

For changed non-trivial behavior, add the smallest check that would fail on a meaningful regression. Reuse existing test style/helpers; mock at external boundaries. Do not rewrite unrelated tests.

Run the narrowest relevant existing formatter, linter, type checker, build, and tests. Broaden verification only when the blast radius warrants it.

## Language priors

- **Python:** built-ins/stdlib first; functions/plain data before stateless classes; no broad `try/except` without meaningful handling.
- **Go:** concrete types first; small consumer-side interfaces only when substitution is needed; no wrapper layers or goroutines without clear lifecycle/cancellation.
- **Rust:** std and concrete owned types first; no traits, generics, lifetimes-juggling, or macros until a second implementation exists; follow the crate's existing error convention — no new error types or one-line wrappers around std calls; clone deliberately, not reflexively to silence the borrow checker; do not test what the type system or std already guarantees.
- **Frontend:** semantic HTML, native controls, CSS, and browser APIs before JS/library machinery; avoid one-off component abstractions and mirrored state. Accessibility is not slop.
- **Markdown/docs:** prose is for what the reader cannot get from the source of truth — point at code, `--help`, or upstream docs instead of restating facts (flags, limits, defaults) that rot; state each fact once; no scaffolding sections, speculative notes for hypothetical situations, or decorative formatting.

## Anti-slop review

After implementation, inspect the diff once for removable complexity:

- **delete** unnecessary code/files/tests/config;
- **reuse** existing code;
- **stdlib/native** replace custom machinery;
- **yagni** remove speculative abstraction/options/defensive paths;
- **shrink** express the same behavior more simply without becoming cryptic;
- **test-noise** remove redundant, trivial, implementation-coupled tests;
- **rot** replace prose restating a source of truth (code, `--help`, git, upstream docs) with a pointer to it;
- **dependency** remove unnecessary packages;
- **scope** revert unrelated changes.

For each finding, identify what can be removed and what replaces it, if anything. Simplify only when requested behavior and required guarantees remain intact.

## Never optimize away

Do not use minimalism to skip root-cause analysis, trust-boundary validation, realistic error handling, security/privacy, cleanup/cancellation/concurrency correctness, accessibility, repository-required checks, or explicitly requested behavior.

A tiny patch in the wrong place is still bad engineering.
