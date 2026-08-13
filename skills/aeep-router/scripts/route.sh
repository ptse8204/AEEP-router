#!/usr/bin/env sh
set -eu
if [ "$#" -lt 2 ]; then
  echo "usage: route.sh CAPABILITY INPUT_JSON_OR_@FILE [extra aeep args...]" >&2
  exit 64
fi
capability=$1
input=$2
shift 2
exec python -m aeep route "$capability" --input "$input" --compact "$@"
