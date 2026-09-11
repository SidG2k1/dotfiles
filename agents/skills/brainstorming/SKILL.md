---
name: brainstorming
description: Use to clarify ambiguous or substantial creative work before implementation. Clear, bounded requests may proceed directly. Keep designs in chat unless the user asks for a spec file or accepts a proposed documented workflow.
---

# Brainstorming Ideas Into Designs

Use enough design work to resolve uncertainty without making routine changes wait on a formal process.

## Choose the Smallest Useful Workflow

Inspect the project context, then choose based on the task:

- **Clear and bounded:** Implement directly. A short approach summary in chat is optional; do not force questions or approval for obvious details.
- **Ambiguous or substantial:** Clarify the important choices, compare genuinely different approaches, and get agreement on the design before implementing decisions the user has not already made.
- **Large and complex:** Propose the full workflow to the user. This may include design discussion, a reviewed spec, an implementation plan, and staged execution. Explain why the extra structure helps and wait for the user to accept it before creating artifacts or requiring extra approvals.

Designs and plans stay in chat by default. Create a spec or plan document only when the user explicitly asks for one or accepts a proposal that clearly says documents will be created. Do not infer permission from the task's size.

## The Process

**Understanding the idea:**

- Check out the current project state first (files, docs, recent commits)
- Assess whether the request is clear enough to implement, needs a short design discussion, or warrants proposing the full workflow
- If the request spans independent subsystems, propose a decomposition before refining details
- Ask questions only when the answers could materially change the implementation
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message - if a topic needs more exploration, break it into multiple questions
- Focus on understanding: purpose, constraints, success criteria

**Exploring approaches:**

- Propose 2-3 approaches when there are meaningful alternatives; skip invented options
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why
- YAGNI ruthlessly - remove unnecessary features from every approach and design

**Presenting the design:**

- Once you believe you understand what you're building, present the design
- Scale each section to its complexity: a few sentences if straightforward, up to 200-300 words if nuanced
- For substantial unresolved choices, get the user's approval before implementation. One approval for a concise design is enough unless separate decisions truly need separate review.
- Cover only the relevant parts of architecture, components, data flow, error handling, and testing
- Be ready to go back and clarify if something doesn't make sense

**Design for isolation and clarity:**

- Break the system into smaller units that each have one clear purpose, communicate through well-defined interfaces, and can be understood and tested independently
- For each unit, you should be able to answer: what does it do, how do you use it, and what does it depend on?
- Can someone understand what a unit does without reading its internals? Can you change the internals without breaking consumers? If not, the boundaries need work.
- Smaller, well-bounded units are also easier for you to work with - you reason better about code you can hold in context at once, and your edits are more reliable when files are focused. When a file grows large, that's often a signal that it's doing too much.

**Working in existing codebases:**

- Explore the current structure before proposing changes. Follow existing patterns.
- Where existing code has problems that affect the work (e.g., a file that's grown too large, unclear boundaries, tangled responsibilities), include targeted improvements as part of the design - the way a good developer improves code they're working in.
- Don't propose unrelated refactoring. Stay focused on what serves the current goal.

## Optional Spec Document

Only enter this section if the user asked for a spec file or accepted a proposed workflow that includes one.

- Save it to the user's requested path, or `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` if they did not name one.
- Write the prose per the `agentish-to-english` skill.
- Do not commit it unless the user asks or the repository's instructions require it.

**Spec Self-Review:**
After writing the spec document, look at it with fresh eyes:

1. **Placeholder scan:** Any "TBD", "TODO", incomplete sections, or vague requirements? Fix them.
2. **Internal consistency:** Do any sections contradict each other? Does the architecture match the feature descriptions?
3. **Scope check:** Is this focused enough for a single implementation plan, or does it need decomposition?
4. **Ambiguity check:** Could any requirement be interpreted two different ways? If so, pick one and make it explicit.

Fix any issues inline. If the accepted workflow calls for user review before planning, ask for it now.

**Implementation:**

- If the user asked for implementation and the design is settled, implement directly unless they accepted a workflow with a planning stage.
- If a detailed plan would help, propose it in chat or invoke the writing-plans skill. A file is still optional and requires user approval.

## Visual Companion

A browser-based companion for showing mockups, diagrams, and visual options during brainstorming. Available as a tool — not a mode. Accepting the companion means it's available for questions that benefit from visual treatment; it does NOT mean every question goes through the browser.

**Offering the companion (just-in-time):** Do NOT offer it upfront. Wait until a question would genuinely be clearer shown than told — a real mockup / layout / diagram question, not merely a UI *topic*. The first time that happens, offer it then, as its own message:
> "This next part might be easier if I show you — I can put together mockups, diagrams, and comparisons in a browser tab as we go. It's still new and can be token-intensive. Want me to? I'll open it for you."

**This offer MUST be its own message.** Only the offer — no clarifying question, summary, or other content. Wait for the user's response. If they accept, start the server with `--open` so their browser opens to the first screen automatically. If they decline, continue text-only and don't offer again unless they raise it.

**Per-question decision:** Even after the user accepts, decide FOR EACH QUESTION whether to use the browser or the terminal. The test: **would the user understand this better by seeing it than reading it?**

- **Use the browser** for content that IS visual — mockups, wireframes, layout comparisons, architecture diagrams, side-by-side visual designs
- **Use the terminal** for content that is text — requirements questions, conceptual choices, tradeoff lists, A/B/C/D text options, scope decisions

A question about a UI topic is not automatically a visual question. "What does personality mean in this context?" is a conceptual question — use the terminal. "Which wizard layout works better?" is a visual question — use the browser.

If they agree to the companion, read the detailed guide before proceeding:
`skills/brainstorming/visual-companion.md`
