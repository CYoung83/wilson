# CLAUDE.md — Wilson Project

This file provides guidance to Claude Code and any Claude instance working
with this repository. It is the living strategic and technical brief for Wilson.
Update it as decisions are made and the architecture evolves.

---

## What Wilson Is

Wilson is an open-source AI reasoning auditor.

**Atomic function:** Wilson removes the advantage afforded to those who will lie.

**Mission statement:** Make auditable truth move at the same speed as
disinformation.

**The problem:** Bad actors flood information channels with volume. AI systems
amplify this by generating plausible-sounding content with no verifiable
evidence trail. Fact-checkers, opinion writers, and reactive debunkers all
exist — but they lose to volume. Wilson removes that structural advantage.

**The solution:** Reconstruct the decision chain behind any AI-generated output
with enough granularity to verify claims against primary sources to a legal
standard. Not an opinion. Not a rating. A documented evidence trail that shows
its homework and holds up in court.

---

## Core Principles

These are non-negotiable and inform every architectural decision:

1. **Everything Wilson produces is independently verifiable.** If Wilson says
   something is false, it can hold that stance because it is provable to a
   legal standard.

2. **Binary where binary is possible.** Claims are verifiably true or false
   against primary sources. No hedging on things that are knowable.

3. **Where binary isn't possible, surface the strongest argument for and
   against — then return determination to the human.** Wilson does not make
   decisions. It makes decisions auditable. It respects human agency rather
   than replacing it.

4. **Show homework to a legal standard.** The evidence trail must be
   reconstructable and defensible, not just plausible.

5. **Open source because auditability requires transparency.** A proprietary
   Wilson is just another black box — which is exactly the problem it exists
   to solve. Wilson only has power if it's trusted. It can only be trusted if
   it's auditable. It can only be auditable if it's open.

6. **Retroactive deployability.** Wilson does not need to be in the loop when
   a decision is made. It needs to reconstruct what happened after the fact
   with enough fidelity to assign accountability. Courts don't prevent crimes
   in real time — they reconstruct them with enough rigor to deter future
   violations. Wilson is forensic infrastructure for the AI era.

7. **No corporate dependency in the core pipeline.** Every component must be
   replaceable with open-source alternatives. Wilson cannot be captured.

---

## Elevator Pitch

For over a decade, bad actors have weaponized information volume. Flood the
zone with enough noise and the truth gets buried — not because people can't
recognize lies, but because there aren't enough hours in the day to audit
everything that claims to be true.

Wilson is the antidote.

An open-source reasoning auditor that removes the advantage afforded to those
who will lie — not by silencing anyone, but by making verifiable truth move at
the same speed as disinformation. Wilson reconstructs the decision chain behind
any AI-generated claim, verifies it against primary sources to a legal
standard, and shows its homework in a way anyone can check.

The goal isn't to win arguments. It's to make the zone unfloodable.

Any claim that passes through Wilson carries a transparent evidence trail. Any
claim that doesn't — starts to look like it has something to hide.

---

## Proof of Concept: Legal Citation Verification

**Why legal first:**
- 1,222+ documented cases of AI hallucinations in court filings (Charlotin
  database), accelerating in frequency
- Binary verification: a citation either exists in the cited source or it
  doesn't. No editorial judgment required.
- Real financial consequences: monetary sanctions, bar referrals, cases
  dismissed. The customer has both budget and existential motivation.
- Existing infrastructure: CourtListener, eyecite, CAP provide the
  verification layer without proprietary dependencies.
- A pre-filing Wilson check would have prevented every sanctioned case in
  the Charlotin database.

**First dataset:** Charlotin AI Hallucinations database
- 1,222 cases identified, Q2 2023 to present
- 810 USA cases, 468 involving licensed lawyers
- CSV available at data/Charlotin-hallucination_cases.csv
- Accelerating: roughly 35+ new cases per two-week period as of March 2026

**Smoke test target (Phase 6):**
Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339 (11th Cir. 2019)
— known fabricated citation from Mata v. Avianca, the first major publicized
hallucination case (May 2023). CourtListener should return NOT FOUND.

---

## Larger Vision

Legal is the proof of concept. The pattern applies wherever AI-assisted
decisions carry real consequences without independent accountability:

- Military targeting decisions (Maven Smart System / Operation Epic Fury)
- Medical diagnosis
- Financial recommendations
- Election integrity (California sheriff Bianco case — AI fabricated quotes
  in legal defense of ballot seizures)
- Legislative drafting
- Congressional oversight of executive branch AI use

The post-Turing threshold Wilson is designed to meet: Can the machine be wrong
in a way that's detectable, correctable, and documentable — and can it show
you exactly where and why? Current LLMs fail this test. Wilson is designed
to pass it.

---

## Technical Architecture (Current Understanding)

Wilson v0.0.1 is a pipeline, not a model:

```
Input (legal brief or any text)
    ↓
Citation Extraction (eyecite)
    ↓
Citation Validation (CourtListener API / local bulk data)
    ↓
Quote Verification (does the quoted text exist in the cited source?)
    ↓
Evidence Trail (structured output showing each verification step)
    ↓
Verdict (VERIFIED / NOT FOUND / MISREPRESENTED) + full reasoning chain
```

**Key dependencies:**
- eyecite — legal citation extraction (BSD license, Free Law Project)
- CourtListener — case lookup and verification (CC BY-ND)
- Harvard CAP — full case text for quote verification (CC0)
- pandas — data analysis
- python-dotenv — credential management

**Design constraints:**
- No cloud dependencies in core pipeline
- Air gap capable from day one
- No proprietary dependencies
- All API tokens in .env, never committed
- Toolbox container is fully reproducible from requirements.txt + runbook

---

## The Bias Map (Future)

Beyond individual citation verification, Wilson's larger technical goal is to
characterize systematic failure patterns:

- Not just "this citation was fabricated" but "this category of legal argument
  produces fabricated citations under these conditions with this frequency"
- The Plinko analogy: you can't reverse a specific ball drop, but if you run
  the simulation enough times you can identify which peg is misaligned
- The bias map is the pattern across many decisions, not a verdict on any
  single one
- This is what transforms Wilson from a pre-filing checker into forensic
  infrastructure

---

## What Wilson Is Not

- Wilson does not make decisions. It makes decisions auditable.
- Wilson does not silence anyone. It makes the evidence visible.
- Wilson is not a fact-checker with editorial bias. Binary verification
  has no opinion.
- Wilson is not a competitor to AI systems. It is the accountability layer
  those systems cannot provide for themselves.
- Wilson is not a proprietary product. A closed Wilson defeats its own purpose.

---

## Project Status

**Current phase:** Infrastructure setup (Runbook Phase 5)
**Dev environment:** iMac 27" (2017), Fedora Silverblue, wilson-dev toolbox
**Storage:** TrueNAS NFS at /mnt/wilson-data/
**Local inference:** Ollama on AI rig (5090, 96GB RAM) at 10.27.27.201:11434
**Next milestone:** Phase 6 smoke test passing

**Founder background:**
- Navy submarine veteran (2010-2021), ETR/ITS(EW)
- GS-13 Training and Exercise Program Specialist, USNORTHCOM Special Activities
- Built benchmark training program for National Military Command System —
  still in use at all nuclear C2 sites
- TS/SCI cleared
- SDVOSB registered: National Standard Consulting LLC
- Operating on integrity as non-negotiable — same value system that built
  the NC3 training architecture applies here

---

## Key Relationships

**James McMurry** — CEO ThreatHunter.ai, Signal contact
- Built MILBERT (defensive cyber threat analysis) and Norby (cybernetic
  digital twin of his own reasoning, named after Norbert Wiener)
- Adjacent but complementary: MILBERT is the threat detection layer,
  Wilson is the upstream accountability layer
- Shared cognitive architecture: contingency planning as foundation of
  everything, human interceding to break AI loops

**Clem Spriggs** — Enterprise IT/cybersecurity sales (Wiz background)
- Referred by Vince Montano
- Question: subcontracting path to prime as SDVOSB

**Damien Charlotin** — Academic maintaining the hallucination cases database
- Primary dataset source
- His database is Wilson's first real-world validation target

---

## Codename

Wilson — named for the volleyball in Cast Away. Something real built under
duress because survival required it. A thinking partner that keeps you sane
when the system breaks down around you.

---

## Instructions for Claude Code

When working in this repository:

1. Read this file and wilson-dev-runbook.md before making any significant
   changes.

2. Wilson's core pipeline must remain verifiable. Every function should be
   traceable. If you can't explain why a step exists, it shouldn't be there.

3. Prefer explicit over implicit. Wilson is an auditing tool — its own code
   should be auditable.

4. No proprietary API dependencies in core verification logic. CourtListener,
   eyecite, and CAP are the primary sources. Other APIs may be used for
   supplementary data but cannot be required for core function.

5. Every output Wilson produces must include a reasoning trace — not just
   a verdict but the evidence chain that produced it.

6. When in doubt, ask. This project is being built by someone learning the
   technical stack in real time. Explain what you're doing and why.

7. The mission is not to build a clever product. The mission is to remove
   the advantage afforded to those who will lie. Every technical decision
   should serve that mission.
