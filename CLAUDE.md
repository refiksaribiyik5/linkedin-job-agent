# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository State

This repository contains a full working implementation of LinkedInBot V1 (`LinkedInBot-Roadmap.md` milestones M1 through M10.2), validated end-to-end against a real LinkedIn account and real config in a Bootstrap run. It is a git repository with full commit history. The tech stack is decided and built out: Python, Playwright, PostgreSQL, Docker Compose, Anthropic (LLM), APScheduler — see `LinkedInBot-TDD.md` for the full technology-decision record.

**Faz 11 (Production Hardening)** in `LinkedInBot-Roadmap.md` is complete — the small, deliberately minimal set of pre-deployment fixes identified during a production-readiness review has landed. The project is currently in **Faz 12 (Production Verification)**: proving, against the real account, that the system actually runs unattended and that backups actually work — the standard M10.1 originally specified but never verified. Once Faz 12 passes, V1 is feature-complete for its actual deployment model (one technical user, localhost, Docker, no external customers, no SaaS) and the project moves from active development to daily operational use. A larger set of possible improvements was identified during the same review and intentionally postponed — see the Roadmap's "Ertelenen Kapsam" (Postponed Scope) section for what was cut and why.

## Product Summary

**LinkedInBot** is a personal, single-user AI system that automates LinkedIn job discovery for one user (Turkish-market, Istanbul-based, entry-level corporate roles). It scrapes/collects job postings, filters them, scores companies and job-fit, and produces a Markdown report. **V1 explicitly excludes automated applications** — the human always applies manually via a link in the report. See PRD Section 1 for full in/out-of-scope lists.

### Core pipeline (PRD Section 10)

The system is meant to be built as a linear, modular pipeline — each stage should be independently swappable per NFR-8/NFR-5:

1. **Trigger** — scheduled (default every 2 days) or manual; mutually exclusive, no concurrent runs (Section 14).
2. **Session Validation** — verify LinkedIn session is still valid; fail loudly, never silently.
3. **Collection** — scrape raw postings matching configured location + broad role keywords.
4. **Normalization** — map raw data into the internal Job Posting model (Section 15.2).
5. **Historical Cross-Reference** — diff against persisted history to classify each job as New / Seen / Updated / Closed.
6. **Filtering Engine** — apply filters **in this order** (cheap/binary first, expensive/semantic last, to minimize LLM cost per NFR-9/Section 11.4): Location → Experience Level → Department Relevance (semantic, LLM-based).
7. **Company Quality Scoring** — 0-100 score from weighted sub-dimensions (Section 12.1); unrated companies are flagged, never silently dropped.
8. **AI Matching Engine** — 0-100 AI Match Score + mandatory rationale (≥3 bullet points) per job (Section 13).
9. **Ranking & Grouping** — group by department cluster; compute Top 10 by AI Match Score.
10. **Report Compilation** — Markdown, grouped by department + Top Matches section (Section 16).
11. **State Update** — mark reported jobs "seen", update closed jobs (history is append-only, never deleted — NFR-11).
12. **Logging** — persist a Run Log record (counts, status, errors) per run (FR-15).

### Architectural constraints that matter for implementation

- **Not stateless**: duplicate/closed/new detection requires a persistent Job History Store keyed by a stable Job ID across runs. Don't design any stage assuming a clean slate each run.
- **Config vs. logic separation is a hard requirement** (FR-13, NFR-6): target location(s), department taxonomy, experience-level list, Company Quality Score threshold (default 50), AI Match Score threshold (default 60), schedule interval (default 2 days), and Top Matches count (default 10) must all live in human-readable config, never hardcoded. See Section 17 for the full parameter table.
- **Every score needs a rationale** — AI Match Score is never shown without an explanation of its components (department, experience, location, company quality, career-goal alignment). Company Quality Score is never silently excluded when unrateable — it's surfaced as "Unrated" instead.
- **Borderline bucket, not hard cutoffs**: scores near a threshold (e.g. AI Match Score 55-60 when cutoff is 60) go into a separate low-priority section rather than being dropped, to avoid silent false negatives (FR-16, Section 20 EDGE-11).
- **Semantic, bilingual matching**: department/role relevance matching must go beyond keyword lookup — it needs to catch semantically-similar titles (including Turkish-language and localized variants) via a confidence score against a configurable threshold (Section 11.2, EDGE-2).
- **Idempotency**: a manual trigger firing right before/after a scheduled run must not produce duplicate report entries or corrupt state.
- **LLM cost control**: cheap deterministic filters (location, experience level) run before any LLM call; only jobs passing those go through semantic/AI scoring.

### Data entities (conceptual, Section 15)

`User Profile`, `Job Posting` (raw), `Company Profile`, `Evaluated Job` (scored, links Job Posting + Company Profile, carries Status: New/Seen/Updated/Closed), `Report`, `Run Log`. Relationships: Company Profile 1→N Job Posting; Job Posting 1→1 Evaluated Job; Evaluated Job N→N Report (a still-open strong match can reappear in Top Matches across multiple reports); Run Log 1→0..1 Report (a run with no new/changed content may produce no report body beyond a status line — see EDGE-7).

### Future roadmap (do not build now, but avoid designs that preclude it)

Phase 2 (Career Intelligence: job summaries, company intelligence, skill-gap analysis, salary estimation, personal dashboard, notifications, output integrations like Notion/Sheets/Email) → Phase 3 (Application Enablement: CV optimization, cover letters, automated Easy Apply, application tracker) → Phase 4 (Career Growth: AI career advisor, interview prep, career trend analysis). Phase dependencies are explicit in Section 18 — e.g. Automatic Easy Apply must not ship before CV Optimization matures.
