# Career Goal Alignment

You are evaluating how well a job posting aligns with a candidate's
stated career goals. This is a semantic comparison, not a keyword
match - a job can be a strong fit even if it does not literally repeat
words from the candidate's career goals, and a poor fit even if it
shares surface-level vocabulary with them.

## Candidate's stated career goals

${career_goals}

## Job posting

Title: ${job_title}

Description:
${job_description}

## Task

1. Judge how well this job posting aligns with the candidate's stated
   career goals.
2. Produce an alignment score between 0.0 and 1.0, where 1.0 means the
   job is a clear, strong step toward the stated goals, and 0.0 means
   it has no meaningful relationship to them.
3. Briefly justify the score using only evidence from the career goals
   and job posting above - do not assume information that is not
   present in either.

Do not produce a final 0-100 match score or a hiring recommendation -
only report the alignment score and your justification. That score is
combined with other signals separately, outside of this evaluation.
