# Experience Level Inference

You are evaluating whether a job posting matches one of a candidate's
accepted experience levels. This evaluation is only performed when a
simple rule-based check on the title and description was inconclusive -
treat this as a genuinely ambiguous case that needs careful reading.

## Accepted experience levels

${accepted_experience_levels}

## Job posting

Title: ${job_title}

Description:
${job_description}

## Task

1. Determine whether this job posting matches one of the accepted
   experience levels listed above.
2. If the title and the description text seem to disagree about the
   required seniority (for example, a junior-sounding title but a
   description that asks for several years of experience, or vice versa),
   the description text is authoritative - base your judgment on it.
3. Watch for seniority signals that would disqualify a posting even if it
   is not explicitly labeled with a senior title (e.g. "3+ years",
   "Manager", "Team Lead") - with the exception of "Management Trainee"
   style programs, which are entry-level by design despite the word
   "Manager" appearing in the title.
4. Briefly justify your conclusion using only evidence from the title and
   description above.

Report whether the posting matches an accepted experience level (yes/no),
which level it most closely matches if any, and your justification.
