FROM aeep-toolkit-v2/capture-policy-local-tag-20261021:control
USER 0:0
COPY --chmod=0444 candidate/SKILL.md /opt/dependencies/stack-check/SKILL.md
COPY --chmod=0444 candidate/LICENSE /opt/dependencies/stack-check/LICENSE
RUN ["/bin/mkdir", "-p", "/etc/codex/skills"]
RUN ["/bin/chmod", "0555", "/opt/dependencies/stack-check", "/etc/codex/skills"]
RUN ["/bin/ln", "-s", "/opt/dependencies/stack-check", "/etc/codex/skills/stack-check"]
USER 65534:65534
