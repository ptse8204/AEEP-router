# Private Langfuse host loopback carrier

Docker recorded a request to bind the web port to the Mac loopback.
The web container was attached only to an internal bridge. Docker's
maintainer explains that publication requires a default-gateway network.
This accounts for the failed host health probes after Next.js signaled
readiness. The retained inspect observation was collected after stop.
[Upstream explanation](https://github.com/moby/moby/discussions/53256)

The [exact review](operation-review.json) keeps the private Docker
network and the existing images. The ordinary exporter connects to
the same localhost address. A narrow host listener passes three
allowed request shapes through Docker exec to the verified web
container. Only the exact canonical minimized receipt can be
posted. Authorization and replies are transient.

The [synthetic checks](check-result.json) verified the request
restrictions. The exact Compose adaptation and disjoint subnet
also passed inert checks. Real health, trace ingestion and export
disablement remain unverified. The repeat awaits operator approval.
