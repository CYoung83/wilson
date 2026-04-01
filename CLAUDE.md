# CLAUDE.md

This file provides guidance to Claude Code and other AI coding
assistants working in this repository.

## Project Purpose

Wilson is an open-source AI reasoning auditor. The atomic
function: Wilson removes the advantage afforded to those
who will lie.

Everything Wilson produces must be independently verifiable.
See README.md for full project context.

## Architecture

Core pipeline: eyecite citation extraction → CourtListener
verification → reasoning trace generation → verdict with
evidence chain.

## Coding Standards

- Every function must include a docstring explaining what it
  does, why it exists, and what failure looks like
- No proprietary dependencies in core verification logic
- All outputs must include the reasoning chain that produced
  them — Wilson eats its own cooking
- Prefer explicit over implicit — this is an auditing tool,
  its own code should be auditable

## Key Dependencies

- eyecite — citation extraction (BSD)
- CourtListener API — case verification
- pandas — data analysis
- python-dotenv — credential management

## Environment

- Python 3.12+
- Virtual environment: venv/
- API credentials: .env (never committed)
- Local bulk data: /mnt/wilson-data/ (never committed)

## Current Milestone

Coherence checking — auditing whether a citation supports
the proposition it's cited for, not just whether it exists.
