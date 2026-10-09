# Offline evaluation fixtures

These three tasks test the evaluation workflow with scripted file edits. Both arms
have the same editing capability; treatment also receives the captured candidate.
No model interprets that candidate, and no benefit is inferred from these results.

The trivial edit repairs one word. The complex edit renames an interface across
two files while preserving a third file and unrelated comments. The adjacent
task preserves its input. Expected artifact digests were made from independent
literal results. They stay with the coordinator; workers receive only current
input files and requested changes.

The suite explicitly retains these public synthetic output files for verification.
General suites default to retaining no output contents. The nested
`resources/evals` sentinel tests exclusion from the deployed candidate payload.
The execution command will be documented after its controlled replay passes.
