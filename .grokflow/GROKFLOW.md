# grokflow protocol (run 20260902-542ec4)

This branch is driven by an automated pipeline. Agents working on it MUST follow these rules.

- Work only on branch `grokflow/telegram-media-downloader-bot-aiogram-3-20260902-542ec4` of `scarrymany/bot-tg-media`. Never push to `main`.
- The task is in `.grokflow/spec.md`. The definition of done is `.grokflow/acceptance.md`.
- Implement in phases as listed in the spec. After EACH phase: run the tests, commit, push.
  Commit message prefix: `[grokflow build <n>/<total>] <what changed>`.
- Never rewrite history on this branch (no force-push, no rebase of pushed commits).
- Do not edit `.grokflow/spec.md`, `.grokflow/acceptance.md` or this file. You MAY add files under `.grokflow/reports/`.
- Preferred model for coding agents: grok-4.6 with reasoning effort xhigh.
- Progress and final reports are posted as comments on the tracking issue: https://github.com/scarrymany/bot-tg-media/issues/1
  Optionally also write the same JSON to `.grokflow/reports/<phase>-<seq>.json` and push it.
- Every report must be honest: list what was NOT done or NOT verified.
