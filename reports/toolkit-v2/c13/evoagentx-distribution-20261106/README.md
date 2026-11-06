# EvoAgentX source and distribution audit

The [wheel audit](result.json) matched the published 0.1.4 wheel to
seven of eight reviewed source files and matched all 18 base requirements.
The wheel's model initializer omits the Novita module import present at
the [pinned commit](https://github.com/ANative-Lab/EvoAgentX/blob/d77fd6b9a3e76c8dd83bebe3374c53a3f5d16f54/evoagentx/models/__init__.py).
Use the source commit for the runtime. The wheel remains available for
audit and has not been installed.

The [source acquisition](source-result.json) verified 262 Git blobs,
including all 258 files under the package directory and four top-level
build and notice files. It staged those files privately from one bounded
12,296,881-byte archive. It retained no unrelated repository assets.
The exact source is available for an offline build once the dependency
artifacts are resolved and reviewed. No upstream code ran.

The selected upstream methods remain `WorkFlowGenerator.generate_plan`
and `build_workflow_from_plan`. The former invokes the reviewed
`BaseLLM` boundary. The latter derives edges from matching port names.
The AEEP adapter must validate that ports and capabilities bind to the
operator's allowed inventory before passing an inert `GoalSpec` to
the existing stack planner. The source acquisition does not establish
a working runtime or proposal. Provider authority remains separate.

## Offline runtime build

The [Linux dependency check](verified-candidates.json) verified 87 wheel
candidates across 805 requirement-marker checks. The [wheel audit](acquisition-result.json)
verified all 115,469,721 bytes and found no wheel startup hooks. Four
packages report license information through package metadata or alternate
notice names. This is private engineering evidence.

The [runtime](evoagentx-runtime-result.json) built from the pinned source
and the 87 wheels. The [first check](evoagentx-runtime-diagnosis.json)
passed its socket boundary and then stopped at an eager Docker SDK import.
The base dependency list omits the Docker SDK. The traceback also reported
asyncio selector cleanup after the socketpair restriction. Both operations
settled. The retained image has no Docker socket mount or provider
credentials. Graph-builder execution and actual proposal generation
remain open.

## Proposal-only continuation

The [static audit](proposal-runtime/overlay-report.json) traced the eager
imports through optional toolkits, long-term memory, storage and code-test
operators. The proposed overlay changes five support files. It preserves
the pinned planner and graph-builder methods, excludes optional toolkit
registration and disables persistent memory for this runtime. The
remaining 83 upstream modules have no unresolved static imports against
the existing wheelhouse. This does not verify dynamic imports.

The [exact repeat review](proposal-runtime/evoagentx-runtime-build-review.json)
uses one COPY-only layer over the retained image. The reviewed syscall
profile permits private Unix socketpairs for asyncio and still denies new
network sockets and connections. The proposed check exercises the real
graph builder on typed local inputs. It requires approval under the repeat
rule. Provider-backed proposal generation remains a separate gate.

## Approved repeat and planner handoff result

The [approved repeat](proposal-runtime/evoagentx-runtime-result.json)
passed. The retained image ran the real graph builder on typed inputs.
The sandbox verified private Unix socketpair communication and denied
other socket creation. The build and check settled 2 operations.

The [planner handoff](planner-handoff/result.json) then ran the actual
`generate_plan` method up to its one reply callback. It captured
10,156 bytes in a private file, with only the request hash and boundary
observations retained in Git. This check settled one operation with
zero models. The separate [local fixture](planner-handoff/stack-shape-check.json)
exercised the inert AEEP planner and four refusal cases. Neither supplied
a provider response.

Prepare a separate, exact managed-worker review before disclosing the
captured request or starting a model turn. The reply must pass the
reviewed schema and port checks before it reaches the upstream parser.
An accepted graph remains an inert AEEP proposal.
