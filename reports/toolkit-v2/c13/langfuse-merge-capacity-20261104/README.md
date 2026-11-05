# Langfuse merge capacity correction

The prior service attempt applied the smaller scheduling pools. ClickHouse then
rejected its mutation threshold of 20 because the merge pool supported only
16 concurrent tasks. The [stopped log findings](../langfuse-pool-diagnosis-20261104/stopped-clickhouse-constraints.json)
record the relevant keys and values from the owned container.

The [review](operation-review.json) raises only `background_pool_size` from 8 to
16, giving 32 logical slots at the observed ratio of 2. The scheduler and
auxiliary pools, 256-PID cap, images and permissions stay the same. The new
owned namespace preserves both stopped attempts. This is an engineering setting
for one receipt export and readback.

The actual attempt is pending explicit repeat approval. It permits up to 63
new operations on the same grant, preserving all 43 charges, the 3,200-second
ceiling and zero model and cash authority. Preparation verified the Compose
adaptation, XML and bound inputs. No service ran under this review.
