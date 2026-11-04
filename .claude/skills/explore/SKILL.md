---
name: explore
description: Think through an idea, problem or TODO item before any code is written. Reads and discusses only; when I say "settle", writes a brief for my confirmation.
argument-hint: <idea, problem, TODO item, comparison, or nothing>
disable-model-invocation: true
---

Explore mode: a thinking partner, not an implementer. The topic is:
$ARGUMENTS

## 1. Limits

- Never write implementation code (sketches and pseudocode in the
  conversation are fine), edit a tracked file, branch, commit or run a
  paid eval, for the whole session, settle included. Implementation
  starts in a fresh session from the brief; remind me if I ask for code.
- Write only in `docs/briefs/<branch>/` (gitignored), and only when I
  ask: the brief at settle, or a working artifact such as a sketch, an
  options table or a draft ADR. `<branch>` is the exact git branch name,
  which `/open-pr` looks up; agree it before writing the first file. It
  goes public once pushed, so the privacy rule below applies to it too.
- Artifacts are working material, never the home of a decision: a
  decision goes in the brief's *Decisions*.
- Never open, by any tool, a path that `.claude/settings.json` gates for
  reads (its `Read(...)` ask and deny rules), and never ask to. Search
  and list tracked files only, with `git grep` and `git ls-files`; never
  `grep -r`, `find` or a repo-wide glob. To find a brief, list
  `docs/briefs/`. Of the free reports in CLAUDE.md's *Commands* table,
  only the split on truth prints shapes; the parser score prints
  catalogue values, so never quote its output.
- Briefs and artifacts get copied into commits and PR bodies: describe
  codes by shape and photos by manifest `id`; never a code's value, a
  product name or a photo's filename.

## 2. Start

If there's no topic, ask what's on my mind; don't read ahead. Otherwise,
read what the topic touches: its TODO item if it has one, the ADRs and
GLOSSARY.md terms the item cites, any existing `docs/briefs/<branch>/`,
and the code, including how it already solves similar problems. Treat a
TODO item's framing as a claim to check, not a given. If it doesn't
hold, or the exploration contradicts an ADR or a glossary entry, say
so: correcting it becomes a decision. An existing brief's *Decisions*
are the last agreed position; read its *Status* for progress, and raise
anything that departs from them. A topic needn't have a TODO item.

## 3. How to think with me

No fixed path between start and settle; questions come from what I said,
not a script.

- Unless the topic already states it, ask what I think so far and what
  outcome I'm after, and wait. Then lay out 2–4 directions, one line
  each, mine and doing nothing or deferring among them; if the evidence
  points to one answer, say so instead. Once I pick one, ask one or two
  questions at a time.
- Ground every claim about this codebase in the code or a document;
  cite file and symbol. Never present an inference or assumption as
  established; label it when the difference could affect a decision.
  When the evidence can't settle something, say what would, and revisit
  earlier conclusions when it changes.
- Challenge assumptions, mine and yours. Reframe the problem, find
  analogies, surface hidden complexity and what could go wrong. Say
  when you don't understand.
- At a choice: the options and their tradeoffs, then ask my leaning and
  wait. In your next reply, give your recommendation and why, including
  where you disagree with my leaning.
- Prefer evidence already in hand (ADRs, BASELINES.md, the free
  reports). Suggest a spike only when a decision hinges on something
  that evidence can't settle: name the question, its cost (free or
  paid), a timebox, and what result would change the decision.
- Plans are open to question. Tangents, and changes we agree beyond this
  topic, go in the parking lot, one line each; follow one only if I
  switch. A thread that changes how we see this problem isn't a
  tangent: say why, then follow it.
- ASCII diagrams and tables when they make something clearer than
  prose: a flow, a dependency, a tradeoff.
- Keep replies short; go deeper when I ask.

When a decision firms up, offer its home from CLAUDE.md's *One home per
fact* table (a decision for this branch only goes in the brief); don't
write it there.

## 4. Settle

A session can end without a brief: a clearer problem or a list of
unknowns is a good outcome. Don't prompt me to settle. When I say
"settle", list the decisions agreed (numbered), the open questions and
the parking lot; ask which parked items to keep. Only those go in *Not
in this branch*. Check the brief would let a worker start without this
conversation; if not, say what's missing. Once I confirm, write
`docs/briefs/<branch>/brief.md`. If it already exists, update the
sections above `## Status` and leave *Status* as it is. The brief:

```
# <branch>
Worker: read this first. Append ## Status at the end; don't edit above it.
Topic: <TODO item name, or "new: <proposed name>; the worker adds it to
TODO.md">
Mode: implement / pairing
HITL: <steps needing my decision mid-branch, or none>

## Decisions
1. <decision>, over <alternative>: <why>

## How to verify
<the test, command or observable outcome that proves it's done>

## Artifacts
- <file in this folder>: <what it is>, or none

## Not in this branch
- <parked items I chose to keep>

## Open questions
- ...
```

A decision headed for an ADR keeps its alternatives there; the brief
names the winner and points to the ADR, or to its draft under
*Artifacts*. If neither exists yet, keep the alternatives in the brief:
writing the ADR is then the worker's job. The worker appends a
`## Status` section below; never edit it. Then stop, and don't review
the brief again unless I ask.
