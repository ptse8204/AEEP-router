#!/bin/bash
# Run only in an isolated WSL distribution. The Windows job also checks backing storage.
set -euo pipefail
release=$1
source_root=$2
evidence=$3
mkdir -p "$evidence"
exec > >(tee "$evidence/journey.log") 2>&1
uname -a | tee "$evidence/kernel.txt"
if ! grep -qi microsoft /proc/sys/kernel/osrelease; then
    echo 'This check requires actual WSL, not a Linux container.' >&2
    exit 2
fi
command -v curl
check_root=$(mktemp -d /root/aeep-wsl.XXXXXXXX)
mkdir "$check_root/home" "$check_root/project"
printf '%s\n' "$check_root" > "$evidence/workspace.txt"
env HOME="$check_root/home" AEEP_CONFIG_HOME="$check_root/home/config" \
    AEEP_DATA_HOME="$check_root/home/data" UV_PYTHON_PREFERENCE=only-managed \
    sh "$release/install.sh" --bundle "$release/bundle" \
    --agent deepseek-api --project "$check_root/project" --yes
"$check_root/home/data/venv/bin/python" "$source_root/scripts/check_installer.py" \
    --release "$release" --workspace "$check_root/journey"
cp "$check_root/journey/result.json" "$evidence/result.json"
cp "$release/SHA256SUMS" "$evidence/SHA256SUMS"
cp "$release/bundle/release.json" "$evidence/release.json"
