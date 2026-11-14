# SkillRank managed diagnostic completed

The [exact approved run](operation-review.json) passed on GPT-6.1 Sol medium.
The real native scheduler requested both isolated trial slots and finalized
both protected grades. Each trial had a complete receipt, verified token-capture
chain and confirmed worker cleanup. The managed proxy returned to stopped.
Two turns and 25 operations settled with no new unresolved reservations.
[Measured result](managed-result.json)

| Measure | Ordinary control | Required-use arm | Required minus ordinary |
| --- | ---: | ---: | ---: |
| Protected score | 1/1 | 1/1 | 0 |
| Input tokens | 165,873 | 176,420 | +10,547 |
| Cached input tokens | 146,048 | 156,544 | +10,496 |
| Cache-write input tokens | 0 | 0 | 0 |
| Output tokens | 1,525 | 1,646 | +121 |
| Reasoning output tokens | 104 | 101 | −3 |
| Agent wall time | 51.20 s | 57.33 s | +6.14 s |

The provider reports these token counts. Cached and reasoning counts are
subsets of input and output respectively. The receipt confirms that treatment
instructions loaded. Its independent invocation field remains unknown.
The trial is a single engineering diagnostic. Candidate usefulness and AEEP
selection usefulness remain unassessed. Comparisons stay paused.
