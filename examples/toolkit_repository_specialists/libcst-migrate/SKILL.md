---
name: libcst-migrate
description: Use LibCST for Python object or import migrations that require syntax awareness and preservation of comments, strings and formatting.
---

LibCST 1.8.6 is available under `/opt/aeep-specialists` in this reviewed worker.
Add that directory to Python's import path when using its API. Ordinary editing
tools remain available.

For a qualified object rename, use `libcst.parse_module`, `CodemodContext` and
`libcst.codemod.commands.rename.RenameCommand` with the task's exact old and new
names. Create a fresh command for each source file and write only editable files.
This parses source; it does not require importing the repository's modules.
Check the resulting diff, including imports, aliases, comments and string literals.
Some migrations need ordinary edits or additional context; a successful transform
does not prove that the task is complete.

Do not install packages, load project-provided codemods or formatters, edit
unlisted files or contact external services. Use ordinary tools for unrelated work.
