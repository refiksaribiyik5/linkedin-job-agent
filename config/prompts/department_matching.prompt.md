# Department Relevance Matching

You are evaluating whether a job posting belongs to one of a candidate's
target department clusters. Matching must be semantic, not purely
keyword-based: titles that are not a literal match but are clearly in the
same professional field (including Turkish-language or localized title
variants) should still be recognized.

## Target department clusters

${department_clusters}

## Job posting

Title: ${job_title}

Description:
${job_description}

## Task

1. Identify which target department cluster (if any) this job posting
   belongs to.
2. Produce a confidence score between 0.0 and 1.0 for how strongly this
   job posting matches that cluster. A score of 1.0 means an unambiguous,
   clear match; 0.0 means no relation at all.
3. Briefly justify the score using only evidence from the title and
   description above - do not assume information that is not present.

Do not decide whether the job passes or fails any threshold - only report
the department cluster (if any) and the confidence score with your
justification. The threshold decision is made separately, outside of this
evaluation.
