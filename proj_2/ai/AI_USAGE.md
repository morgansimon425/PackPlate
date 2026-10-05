# AI Usage

How the PackPlate team uses AI tools in Project 2, and where to find the
evidence. Every significant AI-assisted change has an artifact file in
[`artifacts/`](artifacts/) recording what the AI proposed, what a human
changed, and how the result was checked.

## Tools

| Tool | Model / version | Used by | Where it runs |
|---|---|---|---|
| Claude Code | Claude Opus 5.5 | Ethan | VS Code extension |
| _TODO_ | | | |

## What we use AI for

- Generating project scaffolding and boilerplate (see
  [01-scaffolding](artifacts/01-scaffolding.md))
- Explaining course requirements and tooling options
- _TODO: add as the project goes (e.g. first drafts of tests, PR review)_

## What we do not use AI for

- _TODO: team to decide. Suggestions:_
  - _Deciding allergen and dietary labelling rules. A wrong "fits" can
    hurt someone, so these are written and reviewed by people._
  - _Merging code no human has read._
  - _Writing M0 eval results or self-assessed rubric scores._

## How AI output is checked

1. Whoever uses AI output reviews it by hand and tests it before
   committing.
2. A different teammate reviews the pull request before it is merged.
3. The person who ran the session writes an artifact file from
   [`TEMPLATE.md`](artifacts/TEMPLATE.md).
4. CI runs the test suite on every push, so a regression blocks the
   merge.

## Artifact index

| # | Artifact | Author | Date |
|---|---|---|---|
| 01 | [Project 2 scaffolding](artifacts/01-scaffolding.md) | Whole team | 2026-10-05 |
