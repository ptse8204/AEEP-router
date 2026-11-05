#!/bin/bash
set -euo pipefail
maven=/root/.sdkman/candidates/maven/3.9.6/bin/mvn
common=(-B --strict-checksums --settings /aeep/settings.xml -Dmaven.repo.local=/cache
        -Dmaven.artifact.threads=2 -Dstyle.color=never -f /aeep/pom.xml)
"$maven" -q "${common[@]}" org.apache.maven.plugins:maven-dependency-plugin:3.6.1:resolve -DincludeScope=test
"$maven" -q --offline "${common[@]}" org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -DoutputType=tgf -DoutputFile=/tmp/tree.tgf
exec /usr/bin/cat /tmp/tree.tgf
