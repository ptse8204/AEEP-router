# AEEP 0.5 cache-affinity routing

`cache_affinity_v1` is disabled by default and affects soft ranking only. Hard
latency, token, cash, and capacity feasibility always use the cold estimate.

The router stores only keyed HMAC scope/state/prefix digests, token counts,
timestamps, cache hits, compaction generation, and reset reason. It never stores
raw prompts, reasoning, email, resume, job, or tool-output content.

Warm probability is the bounded product of identity match, prefix fraction,
half-life freshness, state continuity, and observed reliability. With no prior
observation it is zero. Receipts preserve predicted warm probability and actual
input, cached-input, cache-write, output, and reasoning-output dimensions.

Provider-native and OpenAI-shaped usage are normalized once. Cached and
cache-write tokens must remain subsets of total input; reasoning tokens remain
a subset of output.
