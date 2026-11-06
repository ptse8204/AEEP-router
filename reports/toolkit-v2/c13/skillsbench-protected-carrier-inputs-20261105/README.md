# Protected SkillsBench verifier inputs

The two adapted verifier files are staged privately under
`.aeep/skillsbench-protected-carrier-inputs-20261105/`. The
[bindings](carrier-bindings.json) give the exact case, pack and verifier
digests. The preparation script compiles each draft without importing
it and checks that every original assertion remains unchanged.

Sales Pivot moves three fixed paths to private scratch. Spring Boot
moves its workspace to private scratch and replaces SDKMAN startup with
the pinned Maven executable, offline settings and the same two goals.
The [carrier audit](../skillsbench-integration-deadline-20261105/carrier-readiness.json)
binds the retained nonroot parent and the Maven cache. The protected
Spring runtime still needs its pinned Java home and a check that the
build writes fit private scratch and cannot supply their own verdict.

Both adapted files matched the bindings and had private read-only
permissions. The adaptation check rejected a duplicate source
location. No image was built, and no upstream verifier executed.
The two canonical CLI configurations still need packaged protected
runtimes, reviewed task-use determinations and applicable execution
evidence. The local asset review supplies no provider disclosure.
