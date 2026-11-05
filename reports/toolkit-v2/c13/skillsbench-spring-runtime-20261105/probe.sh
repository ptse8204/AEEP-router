#!/bin/bash
set -euo pipefail
/usr/bin/tar --extract --gzip --file=/aeep/interpreter.tar.gz --directory=/aeep-runtime --no-same-owner --no-same-permissions
exec /aeep-runtime/python/bin/python3.12 -I -S -B /aeep/probe.py
