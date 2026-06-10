# WILSON PROJECT HANDOFF
**Compiled:** June 9, 2026 — extracted from DATUM project knowledge base prior to conversation migration to the Wilson project.
**Purpose:** Establish concrete current state, plan the law firm pilot, and define the verification report output.
**Epistemic note:** Every item is labeled DOCUMENTED (traceable to a project source), MEMORY (from working context), or VERIFY (must be confirmed against the repo or a fresh run before being treated as fact).

---

## 1. Identity and Mission

- **Atomic function (locked principle):** Wilson removes the advantage afforded to those who will lie. [DOCUMENTED — DATUM Project Status, April 2026]
- **Role in the DATUM naming hierarchy:** Wilson is the verification standard (citation audit, reasoning chain verification). DATUM = platform, Apollo = interface, Echelon = intelligence layer, ANCHOR = cryptographic commitment, LEXIS = ontological graph. [DOCUMENTED]
- **License:** Apache 2.0, open source. Locked rationale: auditability requires transparency; a proprietary Wilson is just another black box, which is exactly the problem it exists to solve. [DOCUMENTED]
- **Commercial posture (decided June 9, 2026):** Code stays free. NSC sells implementation, support, managed deployment, the attestation/report artifact, and eventually open-core firm-grade features (DMS integrations, multi-user admin, audit logging). Wilson is the wedge into legal; Nautilus/SAIL are the follow-on sales. NSC retains copyright, trademark, and dual-licensing rights.

## 2. Repository and Environment

- **Repo:** github.com/CYoung83/wilson [DOCUMENTED]
- **Local working copy:** `C:\wilson\v0.1.0` [DOCUMENTED — ORCHESTRATOR_HANDOFF]
- **Venv:** `C:\wilson\v0.1.0\venv\Scripts\` — rebuilt against Python 3.13 (`C:\Users\Chris\AppData\Local\Programs\Python\Python313\python.exe`) [DOCUMENTED]
- **Wilson also runs as a sub-application inside Nautilus:** mounted at `/wilson` in Nautilus's FastAPI, code in `wilson_service/` directory, backend port 8193. The standalone exe and the Nautilus-mounted service are distinct deployment surfaces. [DOCUMENTED]
- **Signed tags:** v0.1.0 and v0.1.1 both have signed tags on origin (ED25519 SSH tag signing in use). [DOCUMENTED]

## 3. Version History and Current State

- **v0.0.5** — Released. eyecite citation extraction, CourtListener integration, Charlotin hallucination database. [DOCUMENTED]
- **v0.1.0** — Settings panel fixed. 36/36 tests passing. Signed tag on origin. Phase 3 embeddings fallback (CourtListener semantic search) complete. Document upload portal (PDF/DOCX/TXT) complete. [DOCUMENTED]
- **v0.1.1** — Four fixes: sse-starlette removed; Phase 2 timeout reduced 30s → 15s; dynamic CSV URL via S3 poll (Charlotin dataset); em-dash encoding fixes. Installer rebuilt at 12.67MB. Signed tag on origin. [DOCUMENTED]
- **Outstanding release task:** installer needs to be manually attached to the v0.1.1 release tag on GitHub. [DOCUMENTED — may already be done; VERIFY]
- **v1.0 Windows executable** "technically runs now" per Chris, June 9, 2026, described as rough. [MEMORY — this conversation]

## 4. Verification Pipeline Architecture

Three-pass design, layers complementary not redundant [DOCUMENTED — Echelon_research]:

1. **eyecite** (Free Law Project) — deterministic citation extraction, regex + database lookup, tested against 50M+ citations. No inference in the extraction path.
2. **CourtListener API** — verifies each citation exists and matches a real case. Catches fabricated citations (binary: exists or does not). **Known limits:** ~10M citations of American case law; cannot verify statutes or law journal articles; rate-limited to 60 citations/minute. CourtListener maintains an 18,117,223-citation graph with bulk data exports.
3. **HHEM-2.1-Open or NLI cross-encoder** — checks whether cited cases actually support the propositions they are cited for (misattributed holdings). HHEM-2.1-Open: CPU, ~1.5s per 2K-token input, <600MB RAM, 0–1 factual consistency score. LettuceDetect (ModernBERT, token-level, F1 79.22% on RAGTruth) noted as a complement for pinpointing unsupported claims. **VERIFY: whether layer 3 is implemented in the current Wilson build or remains spec.**

- **Phase 3 embeddings fallback:** CourtListener semantic search. Complete as of v0.1.0. [DOCUMENTED]
- **Verdict taxonomy:** FABRICATED is a confirmed verdict class (used as a BLOCK trigger in Nautilus). VERIFIED/UNVERIFIABLE/MISMATCHED were used in planning discussion but **the actual verdict enum in code must be read and confirmed — VERIFY before writing any report spec against it.**

## 5. Known Issues and Open Work

- **SSE batch stream bug** on the upload portal — open as of the April status doc. v0.1.1 removed sse-starlette, which may have resolved or rearchitected this. **VERIFY current behavior with a fresh batch upload.**
- **Upload portal summary table** — verdicts not populating correctly. Open. **VERIFY whether still broken in v0.1.1.**
- **24-finding code review fix list** — ready for CC, organized in three priority tiers. Location of the list itself: **VERIFY (likely in the Wilson repo or Drive).** Pilot rule: Tier 1 only; Tiers 2–3 go to Linear tagged post-pilot.
- **GitHub Actions release workflow** with build provenance attestation — planned, not built. [DOCUMENTED]
- **ANCHOR integration** — `anchor.verify()` becomes Wilson's ground truth for DATUM integrity. Planned post-Phase 1. **Explicitly OUT OF SCOPE for the pilot.** [DOCUMENTED]
- **Fresh test count:** last recorded 36/36 at v0.1.0. Run pytest fresh before recording any number (standing rule: never trust a stated count).

## 6. Nautilus Integration Facts (context only — not pilot scope)

- Dispatch loop order in Nautilus: Wilson [7a] → Council evaluation [7b] → DATUM crystallization [7c]. [DOCUMENTED]
- Governance principle **EI-5**: Wilson fabricated citation BLOCK (added Nautilus v0.2.4). [DOCUMENTED]
- Wilson upload blocking: user-sourced inquiry resolutions are pre-screened by Wilson; a FABRICATED verdict blocks the resolution entirely. [DOCUMENTED]
- Pilot deployments use the **standalone Wilson executable only.** No Nautilus dependency may enter pilot scope.

## 7. Market Position and Evidence Base

- **Charlotin AI hallucinations database:** 1,250+ documented cases of AI-fabricated citations in real filings. Locked claim: a pre-filing Wilson check would have prevented every sanctioned case in that database. Wilson polls a dynamic CSV URL via S3 for this dataset (v0.1.1). [DOCUMENTED]
- **Benchmark anchors:** Magesh et al. (Journal of Empirical Legal Studies, April 2025) found a 17% hallucination rate for Lexis+ AI; Paxton AI claims 5.3% as the current competitive threshold. [MEMORY — used in SBIR pitch]
- **Demo case:** Mata v. Avianca (the sanctioned ChatGPT-fabricated-citations brief) is public record and is the cold-call demonstration target.
- **Core differentiator sentence:** nothing leaves the firm's network. Local-first verification is the one claim cloud legal AI cannot make. Say it in every pitch.
- **Strategic frame (June 9, 2026 discussion):** sell where the crash already happened and the requirement is already imposed. Law firms face named-attorney sanctions, judicial standing orders requiring AI-use certification, and malpractice carrier questions. Lance's attorney outreach is the correct channel. MSP/legal-tech consultant channel activates only after a reference deployment exists.

## 8. Pilot Plan (agreed June 9, 2026)

**Phase 1 — Pilot-ready build (timebox 7–10 days).** Definition of done: a litigation attorney with no technical skill installs Wilson from the signed installer, drops in a brief (PDF/DOCX), and receives a verification report without a crash.
- Fix only what is on that path: confirm/fix SSE batch stream behavior; fix summary table verdict population.
- 24-finding list: Tier 1 only. Everything else to Linear, tagged post-pilot.
- Build the **Verification Report** as a first-class artifact (spec below).
- One-page quickstart.
- Out of scope: ANCHOR, LEXIS, Nautilus mounting, DATUM crystallization, any new feature.

**Phase 2 — Proof artifact (2–3 days, before any outreach).** Run Wilson against the Mata v. Avianca brief and a sample of Charlotin-database filings. Produce a two-minute screen recording of Wilson flagging the exact citations that produced real sanctions. This recording is the cold-call asset.

**Phase 3 — Pilot offer.**
- Paid pilot: flat fee $1,500–2,500, 60–90 days. Covers installation, support, end-of-pilot efficacy report.
- Agreement: two pages, Lonica reviews. Grants case-study rights (anonymized by default, named with consent).
- Data collected: counts only — citations checked, flagged by verdict class, attorney-confirmed false positives, time per brief. No client document content leaves the firm.
- Target: litigation firms, 2–15 attorneys, where one named partner can say yes in one meeting. Lance runs the list; Chris runs demos.

**Phase 4 — Compound.** Two completed pilots → published case study → SBIR commercialization evidence → MSP/legal-tech consultant channel conversations → team has a repeatable play.

**Scope guardrail:** the big picture gets exactly one sentence in the entire pilot effort, the closing line of the pilot report ("Wilson is the first deployed component of the DATUM verification standard"). Any task that does not move a lawyer closer to holding the report PDF goes to Linear and waits. A `WILSON_PILOT_DONE.md` one-pager governs CC scope.

## 9. Verification Report Specification (draft — finalize against actual verdict enum)

The report is the product the firm keeps, files, and shows their malpractice carrier.

- Format: clean PDF (HTML render acceptable as intermediate).
- Header: Wilson version, timestamp (infrastructure-anchored, not model-generated), SHA-256 hash of the input document, document filename, citation count.
- Body: one row per citation — citation string, verdict (taxonomy from code — VERIFY), CourtListener match details where verified, reason where flagged.
- Summary block: totals per verdict class.
- Footer: data-boundary statement (what was sent to CourtListener: citation strings only; what never left the machine: document content), plus the single DATUM sentence.
- Future (post-pilot, not now): ANCHOR-signed attestation version of this report becomes the paid artifact tier.

## 10. CC Operational Rules (carry into Wilson sessions)

- One file, one task, stop and confirm.
- PowerShell for all Windows paths; bash mangles them.
- Fresh pytest before recording any test count.
- Interrupt immediately when CC loops without writing code.
- Commit after each logical unit; never touch main.
- Long session degrading → commit, write HANDOFF_phase{N}.md, fresh session opens with "Read the HANDOFF completely, then stop and confirm."
- User switches working directories manually; never tell CC to switch.

## 11. First Actions in the Wilson Project (next session checklist)

1. Fresh pytest run in `C:\wilson\v0.1.0` — record the real count.
2. Read the verdict enum from source — lock the taxonomy for the report spec.
3. Test a batch upload — confirm or close the SSE bug and the summary table bug.
4. Locate the 24-finding list — split into Tier 1 (pilot) and post-pilot Linear issues.
5. Confirm the v0.1.1 installer is attached to the GitHub release.
6. Write `WILSON_PILOT_DONE.md` from Section 8 above before any CC work begins.
