# waza — imported observations (NOT_ASSESSED)

No software executed. No verified safety, benefit, billing or worker-isolation conclusion.

```json
{
  "schema_version": "aeep.toolkit.upstream-observations.v1",
  "backend": "waza",
  "source_revision_asserted": "e534d149d89ae77ea158469fb4d2003804b2ee76",
  "candidate_sha256_asserted": "e0123436e1c1f9ac91e2f895941a8ce3d020031c7f13965884b3483d428c6a25",
  "artifact_sha256": "288b028122eb0e3a5381dcb2e35f8123a7f4926adb8b5775bfad9d2555d660eb",
  "trust": "supplied_unverified",
  "outcome": "NOT_ASSESSED",
  "execution_performed": false,
  "observations": {
    "role_claim": "candidate",
    "evaluation_ref": "37b64baf183aa760447308cb906c9d91f7779138cae1007b63b926053fdf0503",
    "tasks": 3,
    "runs": [
      {
        "task_ref": "5116a81ce58c8cc0b9045a2e26bbd50bb1da399debf4833d169d2befc12eceec",
        "run_number": 1,
        "reported_status": "passed",
        "attempts": 1,
        "cached": false,
        "reported_duration_seconds": 0.0,
        "reported_usage": null,
        "verified_outcome": "unknown",
        "candidate_exposed": null,
        "candidate_invoked": null
      },
      {
        "task_ref": "e9a998292b556a26834cd9a0f0258abb36b4045d2a5000a8c290c94d600bf249",
        "run_number": 1,
        "reported_status": "passed",
        "attempts": 1,
        "cached": false,
        "reported_duration_seconds": 0.0,
        "reported_usage": null,
        "verified_outcome": "unknown",
        "candidate_exposed": null,
        "candidate_invoked": null
      },
      {
        "task_ref": "847c3e06e1c3eed83eef34d2cec910a270a7cf19485c09e25797353e5a82d0d3",
        "run_number": 1,
        "reported_status": "passed",
        "attempts": 1,
        "cached": false,
        "reported_duration_seconds": 0.0,
        "reported_usage": null,
        "verified_outcome": "unknown",
        "candidate_exposed": null,
        "candidate_invoked": null
      }
    ],
    "reported_task_statuses": {
      "passed": 3
    },
    "billing_scope": "unresolved_evaluation_sessions",
    "actual_cash": null,
    "token_total": null,
    "cache_semantics": "unverified",
    "paired_worker_conformance": null,
    "baseline": {
      "role_claim": "baseline",
      "evaluation_ref": "37b64baf183aa760447308cb906c9d91f7779138cae1007b63b926053fdf0503",
      "tasks": 3,
      "runs": [
        {
          "task_ref": "5116a81ce58c8cc0b9045a2e26bbd50bb1da399debf4833d169d2befc12eceec",
          "run_number": 1,
          "reported_status": "passed",
          "attempts": 1,
          "cached": false,
          "reported_duration_seconds": 0.0,
          "reported_usage": null,
          "verified_outcome": "unknown",
          "candidate_exposed": null,
          "candidate_invoked": null
        },
        {
          "task_ref": "e9a998292b556a26834cd9a0f0258abb36b4045d2a5000a8c290c94d600bf249",
          "run_number": 1,
          "reported_status": "passed",
          "attempts": 1,
          "cached": false,
          "reported_duration_seconds": 0.0,
          "reported_usage": null,
          "verified_outcome": "unknown",
          "candidate_exposed": null,
          "candidate_invoked": null
        },
        {
          "task_ref": "847c3e06e1c3eed83eef34d2cec910a270a7cf19485c09e25797353e5a82d0d3",
          "run_number": 1,
          "reported_status": "passed",
          "attempts": 1,
          "cached": false,
          "reported_duration_seconds": 0.0,
          "reported_usage": null,
          "verified_outcome": "unknown",
          "candidate_exposed": null,
          "candidate_invoked": null
        }
      ],
      "reported_task_statuses": {
        "passed": 3
      },
      "billing_scope": "unresolved_evaluation_sessions",
      "actual_cash": null,
      "token_total": null,
      "cache_semantics": "unverified",
      "paired_worker_conformance": null
    }
  },
  "limitations": [
    "Imported status is an upstream claim, not an independent AEEP grade.",
    "Runs, cached diagnostics and evaluation session usage are not added together.",
    "Premium requests and AI credits are not cash; token overlap and complete billing remain unresolved.",
    "Arm labels do not establish matching tasks, optional exposure or worker isolation.",
    "Paths, names, prompts, outputs and diagnostic text are omitted; digests can still identify a study."
  ],
  "content_sha256": "56f8fce761d3247f82cec1a3e3f30083e398bba3d48fbb2f3ebabf2f049e512f"
}
```
