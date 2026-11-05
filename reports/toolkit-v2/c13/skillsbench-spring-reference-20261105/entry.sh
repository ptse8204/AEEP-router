#!/bin/bash
set -euo pipefail
case "$1" in
  solve)
    exec /bin/bash /aeep/solve.sh
    ;;
  grade)
    /usr/bin/tar --extract --gzip --file=/aeep/interpreter.tar.gz --directory=/aeep-runtime --no-same-owner --no-same-permissions
    exec /aeep-runtime/python/bin/python3.12 -I -S -B /aeep/observe.py
    ;;
  *) exit 64 ;;
esac
