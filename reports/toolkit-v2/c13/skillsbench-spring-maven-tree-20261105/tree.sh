#!/bin/bash
set -euo pipefail
/root/.sdkman/candidates/maven/3.9.6/bin/mvn -q -B --offline --settings /aeep/settings.xml -Dmaven.repo.local=/cache -Dstyle.color=never -f /aeep/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -DoutputType=tgf -DoutputFile=/tmp/tree.tgf
exec /usr/bin/cat /tmp/tree.tgf
