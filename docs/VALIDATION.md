# Reliability validation and merge procedure

Every pull request to main runs the complete tests/ suite on Python 3.12 and
3.13 using the committed uv lockfile. It does not receive OpenAI, Qdrant or
Stripe secrets, disables dotenv discovery, and uploads JUnit results. The
existing RAGAS Eval Gate remains an independent check using configured service
secrets; this workflow does not skip, weaken or replace that gate.

Run locally with:

```sh
DOTENV_DISABLED=1 uv run --locked python -m pytest tests -q
```

Regression coverage is added alongside each reliability implementation PR:
backup integrity and safe restore, readiness outage/recovery, public/private
retrieval, chat/admin authorization, empty-evidence refusal and cache updates.
A green unit suite cannot establish live cloud availability, notification
delivery or long-term free-tier suspension behavior. Those require the monitor
and documented live recovery checks.

Before merging, verify that the current PR head has completed all CI checks
successfully, confirm no requested changes/conflicts, and use an expected-head
SHA to avoid merging a newer unverified revision. Re-run CI after conflict
resolution. Do not bypass failures or lower evaluation thresholds to merge.
Unit checks run on main as well to detect integration regressions.

The workflow defines checks but does not change repository branch protection.
Repository owners can make both Python test jobs and the existing eval job
required checks through branch protection. Until then, apply the same rule
operationally for every authorized merge.
