# ARD steering, SkillsBench and cloud feasibility audit

October 2, 2026. Inspected commit `c0609f0e1839ea17bbd4871c028e84e75e26970e`;
the implementation verification digest remains
`b37a3d3d18ac6d775558634fa4d435ac54a7b011c0a531e137726f169d568eca`.
The [check record](ard-skillsbench-cloud-audit-20261002.json) binds the inspected
files and the 41 passing offline checks. Existing local cleanup edits were preserved.

The repository has most of the underlying machinery requested by the pasted
steering plan. Its complete ARD-to-intake-to-evidence-to-admission demonstration
is unfinished. SkillsBench reuse currently covers one pinned offer-letter task
and an exploratory verifier adaptation. There is no completed SkillsBench model
comparison or qualifying SkillsBench case generator. This audit takes the user's
explicit alternative of inspecting implementation and explaining the gaps; it
does not claim to have completed the new implementation plan.

| Steering work | Current implementation | Remaining work |
| --- | --- | --- |
| PR 1: ARD decision and compatibility | `discovery.py` declares a bounded v0.91 subset; plan coverage records the integration decision. | No ARD ADR or upstream contribution rule. No exact upstream commit/conformance snapshot. The CLI still defaults to MCP, so ARD is selectable rather than the established primary external path. |
| PR 2: discovery service and identity | `RegistryQuery`, `PackageRegistryAdapter`, `RegistryCandidate`, CLI search and SQLite candidate persistence exist. Raw ARD entry and digest are retained. | No shared request/result/source-record orchestration. ARD URN exists only inside raw provenance; candidate ID is a metadata hash. Source-registry identity is not normalized. No reviewed external-identity binding into admission. |
| PR 3: ARD conformance fixtures | Nine local tests cover bounded queries, inert results, unsupported contexts, redirects, response failures and fallback. | They are project-authored mock fixtures, not pinned upstream conformance assets. No upstream conformance run is recorded. |
| PR 4: candidate intake | `AssessmentService.inspect_local`, `IntakeDeclarations`, `AssessmentSubject`, provider-package import and explicit reviewed mappings already supply static inspection primitives. | No durable transition tying an ARD discovery record, resolved artifact, inspection and proposed mapping together. ARD candidates deliberately have no executable locator. |
| PR 5: evidence identity | `EvidenceCohortKey`, behavior fingerprints, resolved host digests and assessment environment/recipe/mapping digests bind existing evidence. | External resource ID and artifact identity need an explicit reviewed bridge. The new ARD-specific evidence-reuse and migration requirements are not covered merely by existing cohort tests. |
| PR 6: admission disposition | `ScopedAdmission`, atomic admission, authorization revocation, expiry and runtime applicability checks exist. Reports distinguish useful, no benefit, unsuitable and insufficient evidence. | No unified ADMIT/REJECT/RESTRICT/ASSESS/INCONCLUSIVE/EXPIRED decision object with external-resource lineage. Existing negative reports already avoid compulsory activation. |
| PR 7: three-arm experiment | `assessment.experiment.v2`, `ThreeWayAccessDefinition`, optional exposure, qualification requirements and comparative reporting exist. Twenty-three focused tests passed. | The actual normal/discovery/discovery+AEEP campaign is unfinished. Complete current composed conformance, equal access evidence and current qualification are still required. |
| PR 8: fast path | `assessment/applicability.py` checks admitted execution without starting benchmarks; ordinary routing and task scopes work independently of workers. | No host-facing known-ARD-resource lookup that connects discovery to applicable admission or explicit assessment/fallback. |
| PR 9: configuration profiler | Worker inventories, differential environments, receipt resources, `ActionProfiler` and bounded Codex catalog metrics exist. Missing catalog observations remain unknown. | No complete cross-host lifecycle view from installed through verified. Context-size estimates and positive injection observations do not establish complete exposure measurement. |
| PR 10: recommendations | Conditional assessment reports and portable provider-evidence machinery exist. | No completed ARD-resource recommendation API/page. This should consume the preceding evidence chain. |
| Contributor identity and later compensation | Provider identity already includes publisher, homepage and source repository; optional economic modules are separate. | Complete maintainer/dependency/license/support-link lineage is not normalized through ARD intake. The steering plan explicitly postpones new payout machinery. |

The current ARD adapter sends only a caller-supplied public phrase, requests
`federation=none`, limits response size and time, and does not follow artifact
URLs or expand remote JSON-LD contexts. Unknown fields inside accepted entries
survive in raw provenance; entries declaring unsupported contexts are rejected.
Its search relevance and publisher assertions remain inert metadata. Preserve
these boundaries while adding the missing transitions.

The three-arm report currently puts C-versus-B in the primary result,
A-versus-C in the challenger result, and B-versus-A in `discovery_vs_normal`.
A report surface should label that challenger direction explicitly; it should
not silently call A-versus-C a C-versus-A percentage saving.

The architecture can continue to use `Router`, `AssessmentService`,
`BenchmarkRunner`, `CapabilityDefinition`, `ActionRequest`, existing execution
adapters, validators, `ExecutionReceipt`, `ResourceAccounting`, `TaskScope`,
`AssessmentRepository` and `ReceiptStore`. The new service would orchestrate
existing registry adapters. New provenance/intake/disposition records can use
the existing immutable assessment record store when their lifecycle fits it;
there is no demonstrated need for another database, router or scheduler.

The named classes in the steering plan are suggestions, not completion tests.
For example, `AssessmentSubject` plus `ReviewedMapping` already represents much
of artifact intake and semantic mapping. The missing part is durable discovery
lineage and the explicit transition, not the absence of the name `CandidateIntake`.

The experiment inventory extends beyond spreadsheets:

| Experiment | Retained result | What remains |
| --- | --- | --- |
| SkillsBench offer-letter | Pinned upstream `9a1f4dd5f7659f75707435da3ce854b6e48321d1`; nine current local checks passed. Historical protected reference/grader handoff accepted the correct artifact and rejected three faults. | No qualifying generator, fresh 8/28/105 case set, qualified model candidate or value study. Upstream verifier execution and official reproduction remain unclaimed. |
| Workbook four-arm value | Historical campaign completed 705 executions correctly and reported no measured benefit; reusable-tool control dominated the candidate. | New ARD three-arm evidence and current source/model applicability are separate. Tiny/structured native workbook journeys do not supply them. |
| CSV four-arm value | Historical completed campaign reported no measured benefit; an earlier interrupted campaign retained an unknown reporting cost. | Preserve the negative result and incomplete cost lineage. Do not rerun old trials to obtain a favorable result. |
| Structured-text value | Historical qualification passed; the later value run stopped on a host preflight rejection with insufficient evidence. | Fresh applicable reviewed definitions and trials; the old rejection and cost remain. |
| Search value | Historical qualification passed and a reusable baseline was prepared. The remaining value queue did not start search after text stopped. | Fresh applicable value and native-catalog evidence. |
| Website workflow | Fixed offline SDK build/edit and preservation checks passed; undeclared publishing was refused. | Responsive rendering, forms where required, accessibility, live optional model comparison and explicit deployment-state criteria. No complete website value study or publishing readiness. |

These historical results come from the dated entries and their linked records in
[plan coverage](plan-coverage.md), not from new cloud or model execution in this
audit. In particular, negative workbook/CSV results are completed findings within
their original scope, not missing implementations.

The reasons for unfinished work differ:

* SkillsBench initially needed Linux filesystem outputs adapted to the bounded
  JSON recipe/grader contract, with its oracle outside the trial worker. The
  [September 29 compatibility record](steering-v1-skillsbench-compatibility.json)
  documents this mismatch. The later
  [protected handoff](skillsbench-protected-handoff/result.json) resolved a narrow
  artifact-transfer check. Its [preparation code](skillsbench-protected-handoff/prepare.py)
  still deliberately raises `Exploratory only: qualifying materialization is unsupported`
  in the generator. This is a remaining implementation gap, not just missing approval.
* September 29 delivery steering prioritized native, container-free Mac operation.
  Subsequent work repaired actual sandbox, process cleanup, artifact delivery and
  callback-binding failures. The testing policy and dated records document that
  priority. It explains where effort went; it does not make ARD integration complete.
* Live campaigns encountered disk exhaustion, host rejection, model availability
  differences and later Docker failures. Model/source/backend changes also
  required fresh evidence. Earlier capacity exhaustion was subsequently cleared;
  this audit makes no claim about current subscription capacity.
* Full composed conformance remained unfinished after one actual callback
  succeeded. A successful callback cannot establish the full comparison boundary.
* No specific prior reason was found for leaving the ARD ADR, normalized external
  identity and discovery-aware lookup undone. They are uncompleted steering work;
  a technical impossibility or approval requirement should not be invented.
* Public recommendation surfaces and new funded rewards were expressly sequenced
  after usable comparative evidence. Human comprehension still needs participant
  responses, which software checks cannot supply.

Cloud feasibility depends on which part is moved:

| Destination/scope | Assessment |
| --- | --- |
| Ordinary code work and portable offline checks in Codex cloud | Suitable in principle. The official environment runs a repository checkout with setup scripts. Account access and this repository's cloud configuration were not tested. |
| Complete existing experiment in one Codex cloud chat | Not established. A default task container does not establish the required independently controlled workers, protected oracle, nested sandbox policy, durable grant ledger or authenticated trial inventory. |
| Dedicated Linux VM running the existing AEEP coordinator and Docker workers | Closest fit for Linux SkillsBench adaptation and controlled agent studies. Requires reviewed images, network policy, protected sign-in, current boundary evidence, persistent storage and the missing recipes. No new benchmark engine is needed. |
| Existing three-arm profile unchanged on Linux | Not portable as configured: the composed AEEP arm calls the protected Mac native executor. `NativeSandboxConfig.argv` rejects non-macOS hosts. A new Linux execution binding and conformance, or a remote Mac endpoint, is required. The latter is a hybrid run. |
| Every current Mac production acceptance check on Linux | No. Linux evidence cannot verify this Mac's native sandbox, desktop activation, local configuration restoration or observed resource behavior. A cloud Mac would be a new host cohort, not proof about this machine. |
| Human comprehension | Can be conducted remotely, but still requires an actual participant. |

Official [Codex cloud environment documentation](https://learn.chatgpt.com/docs/environments/cloud-environment)
describes repository containers, setup scripts, setup-only secrets and command
network controls. It does not establish the nested runtime controls needed here.
Thus offline cloud work is plausible; a complete AEEP campaign requires a runtime
preflight, not an assumption that separate chats prove isolation.

The [self-hosted sandbox API](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)
can connect a remote environment through `codex exec-server`. Adopting that
harness would be another adapter/environment review; it is not already the
repository's pinned App Server path. The [Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview)
bills model usage at API rates and hosted sandboxes at container rates. The
current zero-cash assessment authority does not cover those charges or renting
a VM.

For the existing Codex CLI/App Server route, official
[authentication guidance](https://learn.chatgpt.com/docs/auth#login-on-headless-devices)
supports device-code sign-in on headless machines. Repository policy requires
that setup in the operator's terminal, outside agent output capture. Desktop
credentials must not be copied. Cloud model access, subscription capacity and
trial authentication remain unverified; creating a cloud coding task does not
establish any of them.

Cloud preparation must retain the original assessment grant and used counters.
The canonical runtime stores live under ignored `.aeep/`; a Git clone alone does
not contain the live ledger. Before migration, stop overlapping assessment
writers and prepare an explicitly reviewed, credential-free transfer of the
necessary state and dependency closure, with path rebinding and fresh environment
review. Copy neither the entire home directory nor authentication volumes.
Changing host, architecture or backend changes evidence applicability. Existing
arm64 wheel/image pins also need review before selecting an x86 VM.

The minimum next implementation sequence is:

1. Add the requested ARD ADR and supported-subset/conformance pin to
   `docs/adr/` and `ARCHITECTURE.md`. Record the upstream contribution rule in
   `AGENTS.md`; verify the exact upstream specification before adopting it.
2. Extend `discovery.py` and existing store/CLI paths with explicit source and
   resource identity, then connect reviewed local intake through
   `assessment/intake.py`, `assessment/models.py` and `assessment/service.py`.
   Add disposition/lookup behavior through existing applicability and reporting
   paths. Preserve historical serialization and inert search behavior.
3. Build a separately versioned offer-letter recipe through the existing
   `ExecutableRecipeExtension` and `assessment/extensions.py` path. Freeze a
   bounded generator, independent reference, grader and fault fixtures before
   materialization. The current grader's `upstream_equivalent` check requires
   relocation `Yes`; a `No` variation needs an explicitly separate adapted
   acceptance rule. Do not treat all nine unit checks as nine benchmark tasks.
4. Select the cloud runtime and actual candidate before freezing fresh plans.
   Prove shared tool availability, separate workers, protected answers and the
   AEEP arm's execution boundary. Preserve 8 screening, 28 training and 105
   holdout cases per reviewed family, optional invocation during value trials,
   fixed utility thresholds and all incurred assessment costs.
5. Run the offer-letter study and the declared normal/discovery/discovery+AEEP
   comparison through `AssessmentService` and `BenchmarkRunner`. Add further
   pinned SkillsBench tasks only after each task contract and grader are reviewed.
   Keep CSV/text/search and the website workflow in the experiment inventory;
   do not replace their missing results with spreadsheet smoke tests.

Only the audit and existing small offline checks ran in this session. The check
record contains the exact command, file hashes and test counts. Production source,
test definitions, grants and canonical accounting were unchanged. No image,
dependency installation, cloud resource or model trial was created. The full
release suite was not rerun for this documentation-only audit.

Local free space measured 39.19 GiB, below the required 50 GiB reserve, so large
local builds/campaigns are not ready to proceed. The earlier
[cleanup record](validation-temporary-cleanup-20261002.json) already removed
eleven validation directories without confirmed physical recovery. Its 25
observed Time Machine snapshots are a retention-review candidate, not verified
obsolete task resources. Failed diagnostics and canonical evidence must remain.
No additional deletion, Docker restart, snapshot change or cloud provisioning
was performed.
