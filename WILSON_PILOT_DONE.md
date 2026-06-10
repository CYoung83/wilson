# WILSON_PILOT_DONE.md
**Governs all Wilson work until two pilots are signed. Anything not on this page goes to Linear tagged `post-pilot` and waits.**

---

## Definition of Done (one sentence)

A litigation attorney with no technical skill installs Wilson from the signed installer, drops a brief (PDF or DOCX) into the upload portal, and receives a Verification Report PDF without a crash, an error they have to interpret, or a step they have to ask about.

---

## In Scope — the complete list

1. **Verify ground truth first (no code changes until done):**
   - Fresh pytest run in C:\wilson\v0.1.0. Record the real count.
   - Read the verdict enum from source. Lock the taxonomy.
   - Run a real batch upload. Confirm or close the SSE stream bug and the summary-table verdict bug.
   - Locate the 24-finding code review list. Split: Tier 1 stays, Tiers 2-3 to Linear.
   - Confirm the v0.1.1 installer is attached to the GitHub release.

2. **Fix only what blocks the Definition of Done:**
   - Summary table verdicts populating correctly.
   - Batch upload stream completing reliably.
   - 24-finding list Tier 1 items only.
   - Graceful failure: any error a lawyer can hit produces a plain-language message, never a stack trace.

3. **Build the Verification Report (the product):**
   - Clean PDF output.
   - Header: Wilson version, infrastructure timestamp, SHA-256 of input document, filename, citation count.
   - Body: one row per citation — citation string, verdict, CourtListener match detail or flag reason.
   - Summary block: totals per verdict class.
   - Footer: data-boundary statement (citation strings only were sent to CourtListener; document content never left the machine) and one closing sentence: "Wilson is the first deployed component of the DATUM verification standard."

4. **One-page quickstart** an attorney can follow unassisted.

5. **Proof artifact:**
   - Run Wilson on the Mata v. Avianca brief and a Charlotin-database sample.
   - Two-minute screen recording of Wilson flagging the citations that produced real sanctions.

---

## Out of Scope — no exceptions, no matter how good the idea is

- ANCHOR integration
- LEXIS anything
- Nautilus mounting or wilson_service changes
- DATUM crystallization
- GitHub Actions release workflow
- New features of any kind
- Refactoring code that passes its tests
- DMS integrations (iManage, NetDocuments)
- Multi-user, accounts, admin
- UI polish beyond what the Definition of Done requires

If it is not required for a lawyer to hold the report PDF, it does not happen now.

---

## Pilot Offer (fixed — do not redesign mid-outreach)

- Flat fee: $1,500-2,500. 60-90 days.
- Includes: installation, support, end-of-pilot efficacy report.
- Firm grants: case-study rights, anonymized by default, named with written consent.
- Data collected: counts only — citations checked, flagged per verdict class, attorney-confirmed false positives, time per brief. No client document content leaves the firm.
- Target: litigation firms, 2-15 attorneys, one named partner can decide in one meeting.
- Lance runs the outreach list. Chris runs demos. The demo is the Avianca recording plus a live run.

---

## Exit Condition

This document retires when two pilot agreements are signed. Then, and only then, the zoom-out is earned: case study, SBIR commercialization evidence, MSP and legal-tech channel conversations, open-core roadmap.

---

## CC Session Rules (every Wilson session)

- This file and WILSON_PROJECT_HANDOFF.md load at session start.
- One file, one task, stop and confirm.
- PowerShell for Windows paths.
- Fresh pytest before recording any count.
- Save state before every modification. Never delete — move to trash.
- Scope challenge: before accepting any task, CC states which In Scope item it serves. No item, no task.
