# Build only from a separately reviewed local context. No downloads or login.
FROM node@sha256:f32b81066cde10a75dbac96646099533316d94bac4150c55da1636e1f0ffdc46 AS node
FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY codex codex-code-mode-host rg /opt/codex/
COPY codex-resources /opt/codex/codex-resources/
COPY worker-launch worker-config.json codex_metrics.py /opt/aeep/
COPY requirements.toml /etc/codex/requirements.toml
# Both directories exist in each context; baseline has no selected plugin.
COPY dependencies/ /opt/dependencies/
COPY skills/ /opt/skills/
RUN chmod 755 /opt/aeep/worker-launch /opt/codex/codex /opt/codex/codex-code-mode-host /opt/codex/rg && mkdir -p /worker/auth && chown 65534:65534 /worker/auth
ENV PATH="/opt/codex:/usr/local/bin:/usr/bin:/bin"
USER 65534:65534
WORKDIR /workspace
ENTRYPOINT ["/opt/aeep/worker-launch"]
