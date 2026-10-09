# Draft: installed skill payload can differ without content_hash changing

Not published. Reproduced locally with agent-skill-eval 0.7.0, source revision
`59de161f657b82bfaf8f6abe83dfff38552deb21`. The installed `skills.py` matched the
reviewed source hash `977cb376bfdd2954361abf5fa39abb657aa2b2613443cac122da35a36fdf9c64`.

`SkillInstaller._content_files()` excludes any path containing `evals`, `.git`
or `__pycache__`. `SkillInstaller.install()` excludes those directory names only
among the immediate children of the skill root, then uses recursive `copytree`
for other directories. Consequently, nested excluded directories are installed
but are absent from `content_hash()` and `size_metrics()`.

A synthetic skill containing `resources/evals/nested.txt` reproduces this:

1. Compute `content_hash()`.
2. Change that file's bytes.
3. Compute `content_hash()` again: unchanged.
4. Install the skill with `AgentType.FAKE`: the changed file is copied.

The probe also copied synthetic `resources/.git/config` and
`resources/__pycache__/marker.txt`. Top-level `evals` was correctly excluded.
See `probe.py` and `result.json` for the exact source, assertions, hashes and
sandbox checks. The probe used no model, network, credentials or real answers.

This weakens the reported hash's binding to installed behavior and can expose
nested evaluation material if a candidate contains it. It does not establish
that any real user data was exposed.

Suggested correction: enumerate one canonical payload and use that same list
for hashing, size accounting and installation. Add a regression that changing
an excluded nested file either cannot affect installed bytes or changes the
reported identity. Symlinks and non-regular files need an explicit policy too.

AEEP's development fixture bridge now rejects all unlisted payload entries and
stages only its two captured hash-checked files. That local guard protects the
fixed demo; it is not a fix or qualification for arbitrary upstream candidates.
