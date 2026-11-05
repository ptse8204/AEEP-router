# Retained Waza and Copilot archives

Review b9897f6b passed its first data-only pipeline under the recorded standing
operator authority. It downloaded exactly the pinned Waza 0.38.9 Darwin ARM64 ZIP
and Copilot 1.0.85 Darwin ARM64 tar archive, checked their publisher SHA256 values,
and safely extracted three regular files without running them. Exact archive
and file hashes are in acquisition-result.json. There were no retries.

Both archives and all extracted files remain in the owned private .aeep runtime.
Two canonical operations settled; models 0. Response-body bytes are 157,492,008,
not measured wire traffic. The first native backend information checks are a
separate component-scoped pipeline; see ../waza-native-backend-20261104/RESULTS.md.
No old mock run,source test, wheel check, docs check or Docker action was repeated.
