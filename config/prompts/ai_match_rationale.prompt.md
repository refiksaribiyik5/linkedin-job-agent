# AI Match Rationale

You are writing a short, verifiable explanation of why a job posting was
matched to a candidate. You are given only the already-computed signals
below - you do not have access to the raw job posting or company text, and
you must not invent or assume anything beyond what these signals state.

## Computed signals

- Department/Role Relevance score: ${department_relevance_score}
  - Note: ${department_relevance_note}
- Experience Level Fit
  - Note: ${experience_level_fit_note}
- Location Fit
  - Note: ${location_fit_note}
- Company Quality Score: ${company_quality_score}
- Career Goal Alignment score: ${career_goal_alignment_score}
  - Note: ${career_goal_alignment_note}

## Task

Produce a short list of rationale bullet points, one per signal above that
meaningfully supports the match. Each bullet must be grounded strictly in
the corresponding signal and note given above - do not add commentary,
speculation, or claims that cannot be traced back to one of these signals.

Report each bullet as a component/value/explanation triple:
- component: which signal the bullet is about (e.g. "Department/Role
  Relevance", "Experience Level Fit", "Location Fit", "Company Quality",
  "Career Goal Alignment").
- value: the concrete score or fact from that signal.
- explanation: a short, human-readable restatement of the corresponding
  note above.
