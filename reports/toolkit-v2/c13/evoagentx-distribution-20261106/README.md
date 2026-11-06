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
