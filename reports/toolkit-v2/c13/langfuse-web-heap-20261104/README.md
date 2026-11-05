# Langfuse startup heap correction

The approved merge-capacity attempt passed all datastores, Minio bucket setup
and web container creation. Its web process reported successful migrations
and Next.js startup, then hit V8's 640 MiB old-space limit. The stopped
container exited 134 with Docker's OOMKilled flag false. See the
[bounded heap diagnosis](../langfuse-merge-capacity-20261104/stopped-web-heap-diagnostic.json).

The [new review](operation-review.json) raises web and worker old-space caps to
1,024 MiB and container caps to 1,536 MiB. Total active service caps are 5 GiB.
The existing Docker VM reports 7.75 GiB and four unrelated running containers
used about 0.76 GiB when sampled. These are engineering caps for the one-receipt
journey. Production sizing remains a separate workload decision.

Use a fresh owned namespace and preserve all existing containers and volumes.
Reuse every image, the working datastore settings and the 256-PID cap. Keep
the existing 3,200-second and zero-model/zero-cash limits, all 76 operations
charged and the 50 GiB host reserve. One specific repeat needs operator approval.
