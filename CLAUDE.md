# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.
Do not search for this file. You are already reading it.

# Project: Wilson

Open-source AI legal citation auditor. Apache 2.0. github.com/CYoung83/wilson
Atomic function: Wilson removes the advantage afforded to those who will lie.

---

## Session Start Protocol

1. Read WILSON_PILOT_DONE.md completely. It governs all work. Anything not In Scope goes to Linear tagged post-pilot.
2. Read WILSON_PROJECT_HANDOFF.md for current state and verified facts.
3. State which In Scope item the requested task serves before starting it. No item, no task.
4. Stop and confirm understanding before making any change.

---

## File Safety Policy (mandatory, no exceptions)

- NEVER delete files. Move to I:\trash instead.
- Before modifying any file: copy every file to be modified to I:\save_states\YYYYMMDD_HHMMSS\<relative_path>. One timestamp per session.
- After changes and tests pass: write I:\save_states\YYYYMMDD_HHMMSS\CHANGES.md.
- Never commit to main. Check branch before every commit: git branch --show-current
- Do not rewrite working code. If it passes its test, leave it alone.

---

## Off-Limits Paths — NEVER modify
- venv/ (any file)
- .git/ (beyond normal commits; never rewrite history, never touch tags)
- dist/ and any built installer artifact
- tests that currently pass
- requirements.txt without explicit user approval

## Pre-Task Protocol
- Before modifying any file: restate the task in one sentence and list anything uncertain. Wait for confirmation if uncertainties exist.
- Any task touching 3 or more files: present the file list and plan first. No changes until approved.

## Error Handling
- No bare except. Catch specific exceptions with meaningful handling.
- Any error path a user can reach must produce a plain-language message, never a traceback.

---

## Environment

- Project root: C:\wilson\v0.1.0
- Python: C:\wilson\v0.1.0\venv\Scripts\python.exe (Python 3.13). Never bare python or python3.
- Use PowerShell for all Windows path operations. Bash mangles backslash paths.
- ASCII only in all console output: [OK], [FAIL], [ERROR], [SKIP], [WARN]. No Unicode, no emoji.
- Executor model: Qwen3.6-27b via LM Studio (http://100.66.110.110:1234). Secondary: Qwen3.5-9b on 100.109.47.18.

---

## Execution Discipline

- One file, one task. Complete and test before moving to the next.
- Write complete files. No partial writes.
- Never use python -c for multi-step work. Write a .py file and run it.
- Stop after 3 consecutive failed attempts on any single task. Report and wait.
- If a file edit fails twice on the same file, rewrite the whole file in one operation.
- Report blockers immediately. Do not work around them silently.
- Do not start implementing anything without reporting findings first.
- Never state a test count from memory. Run pytest fresh, then report the actual output.

---

## Testing Protocol

- Run the full suite with: venv\Scripts\python.exe -m pytest
- Test before committing. Pass = commit. Fail = fix first.
- Do not delete or modify passing tests.
- Last recorded baseline: 36/36 at v0.1.0. Verify fresh; do not trust this number.

---

## Verification Pipeline (orientation)

1. eyecite — deterministic citation extraction
2. CourtListener API — existence verification (rate limit: 60 citations/minute — respect it in batch code)
3. Charlotin hallucination database — dynamic CSV via S3 poll (v0.1.1)

Data boundary rule: citation strings only may be sent to CourtListener. Document content never leaves the machine. Any code change that would violate this is out of scope by definition.

---

## Current Sprint (pilot preparation)

Definition of done: a litigation attorney with no technical skill installs Wilson from the signed installer, drops in a brief, and receives a Verification Report PDF without a crash.

Out of scope, no exceptions: ANCHOR, LEXIS, Nautilus mounting, DATUM crystallization, new features, refactoring passing code, DMS integrations, multi-user. Full list in WILSON_PILOT_DONE.md.