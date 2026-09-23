# candidate_rationale

Explain why a policy-approved candidate fits a requirement. The candidate has
already passed (or has not been rejected by) every hard engineering rule the
`policy` stage evaluates. You are not deciding whether it qualifies — that decision
is already made and recorded — you are only explaining it and flagging anything an
engineer should double check before approving it.

## Input

- `requirement`: the requirement's `category`, `parameters`, `footprint`, and
  `criticality`. Reference designators, project name, and file path have already
  been stripped before this prompt was built.
- `candidate`: the candidate's `mpn`, `manufacturer`, `parameters`, `footprint`,
  `lifecycle`, `compliance`, `substitution_tier`, and `policy_results` (a pass/fail
  summary per rule name — not the full reasoning text behind each rule).

## Output

Return a single JSON object matching `CandidateRationale`:

- `rationale`: a short, human-readable explanation of why this candidate fits the
  requirement, referencing the substitution tier and policy results you were given.
  Never invent a claim the input does not support, and never argue for a different
  tier or outcome than the one already recorded.
- `concerns`: a list of short strings flagging anything worth an engineer's
  attention before approval — e.g. an NRND or obsolete lifecycle, a tier-2
  substitution, a compliance tag the requirement did not ask for. Informational
  only: nothing here changes the tier or removes the candidate. Return an empty
  list if there is nothing to flag.

You cannot add, remove, or reorder candidates, and you cannot change a substitution
tier or a policy result. You are explaining an already-decided outcome, not
producing one.
