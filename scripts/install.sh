#!/bin/sh
# Release builder replaces the two tokens below with an immutable release and bundle hash.
set -eu
release_base='@RELEASE_BASE@'
bundle_sha='@BUNDLE_SHA256@'
aeep_root="${AEEP_DATA_HOME:-$HOME/.local/share/aeep}"
bundle=''
if [ "${1:-}" = '--bundle' ]; then
    bundle=$2
    shift 2
fi
case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) target=aarch64-apple-darwin; uv_sha=3f61099e261e449527141dbf125629fab33ad696468c8c90cebbac40185a306c ;;
    Darwin-x86_64) target=x86_64-apple-darwin; uv_sha=76638fdcfa91357858771551a1c88de1f7c3b270b33ab1866f8a0618d9e442d8 ;;
    Linux-aarch64) target=aarch64-unknown-linux-gnu; uv_sha=726b72a137fda33565143325f7d31c42cd30ff9ccdf067e00d124d37b4081cb2 ;;
    Linux-x86_64) target=x86_64-unknown-linux-gnu; uv_sha=741ff1f5742c5a4a25d2f829e8395355e43f7a5ae2ebc6368e9ae2df0efb69cf ;;
    *) echo 'Supported: macOS and Linux/WSL on arm64 or x86_64.' >&2; exit 2 ;;
esac
mkdir -p "$aeep_root"
free_kib=$(df -Pk "$aeep_root" | awk 'NR==2 {print $4}')
if [ "$free_kib" -lt 53477376 ]; then
    echo 'AEEP needs 51 GiB free to retain the 50 GiB reserve. Inspect obsolete AEEP staging directories first.' >&2
    exit 2
fi
stage=$(mktemp -d "$aeep_root/staging.XXXXXXXX")
trap 'echo "Installer staging retained for inspection: $stage" >&2' EXIT
verify() {
    if command -v sha256sum >/dev/null 2>&1; then
        actual=$(sha256sum "$1" | awk '{print $1}')
    else
        actual=$(shasum -a 256 "$1" | awk '{print $1}')
    fi
    [ "$actual" = "$2" ] || { echo 'Download checksum mismatch; stopped.' >&2; exit 2; }
}
curl --connect-timeout 10 --max-time 120 --proto '=https' --tlsv1.2 -fLsS "https://github.com/astral-sh/uv/releases/download/0.8.22/uv-$target.tar.gz" -o "$stage/uv.tar.gz"
verify "$stage/uv.tar.gz" "$uv_sha"
tar -xzf "$stage/uv.tar.gz" -C "$stage" "uv-$target/uv"
uv="$stage/uv-$target/uv"
export UV_PYTHON_INSTALL_DIR="$aeep_root/python"
export UV_CACHE_DIR="$aeep_root/cache"
if [ -z "$bundle" ]; then
    case "$release_base" in '@'*) echo 'Use a built release installer or --bundle /path/to/release-bundle.' >&2; exit 2 ;; esac
    curl --connect-timeout 10 --max-time 120 --proto '=https' --tlsv1.2 -fLsS "$release_base/aeep-bundle.tar.gz" -o "$stage/bundle.tar.gz"
    verify "$stage/bundle.tar.gz" "$bundle_sha"
    tar -xzf "$stage/bundle.tar.gz" -C "$stage"
    bundle="$stage/bundle"
fi
# uv reuses a compatible runtime, or downloads its pinned Python distribution.
"$uv" venv --python 3.12.11 "$stage/venv"
"$uv" pip install --python "$stage/venv/bin/python" --require-hashes --only-binary :all: -r "$bundle/requirements.txt"
"$stage/venv/bin/python" "$bundle/finish_install.py" "$bundle" "$stage/venv" "$aeep_root" "$@"
