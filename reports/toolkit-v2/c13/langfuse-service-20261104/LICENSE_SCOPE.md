# Source and license scope

This review concerns private, unmodified upstream services on one Mac. It does
not approve redistribution, hosted access for third parties, enterprise features,
publication or release. Image digests are unchanged from the approved acquisition.

Langfuse release `5e4db922e9021083500cd066249b220a414b7dfe` has an MIT core,
separate enterprise directories and upstream third-party terms. Both startup
scripts match the acquired image files byte for byte. Enterprise keys, FIPS,
in-app agents, AI provider settings, experimental features, SMTP and outbound
telemetry are disabled or unset. Root LICENSE and enterprise LICENSE are retained
privately with their Git blob identities. No enterprise subscription is assumed.

The Minio image SBOM identifies Minio and mc as AGPL-3.0-or-later, including their
exact package versions. Original notices and all image layers remain unchanged.
Its root ownership initializer affects only the newly created volume directory;
bucket creation uses the included upstream mc client.

The Redis image declares Redis 7.4.12. That release's LICENSE.txt identifies
RSALv2 or SSPLv1, and REDISCONTRIBUTIONS.txt identifies remaining BSD portions.
The license files are cached and Git-blob-bound. This check keeps Redis entirely
inside the private network and does not offer Redis or its API to third parties.
No general redistribution or managed-service license clearance is inferred.

Postgres 17.11's image copyright and dependency notices remain in the retained
static inventory. ClickHouse and every supporting base image retain their
original notices. The static image audit records actual hashes, permissions,
package notices and SBOM data; it is not a claim that every dependency uses a
single permissive license. Public distribution requires a separate review.

The new Compose definition adapts the pinned upstream six-service example:
immutable images, finite resources, private networking, localhost-only exposure,
no automatic restart, explicit ownership/bucket steps and direct argv commands.
The upstream application entrypoints, migrations, core server and observations
API remain intact. These environment/permission adaptations are engineering
configuration, not an official upstream deployment certification.
