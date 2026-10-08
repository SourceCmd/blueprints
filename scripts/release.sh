#!/usr/bin/env bash
#
# Build a catalog release: validate every blueprint and write, in dist/,
#
#   index.json       the index: every blueprint's id, kind, format, version,
#                    summary and the sha256 of its file
#   index.json.sig   the detached Ed25519 signature over index.json's exact
#                    bytes (only when a catalog signing key is on this
#                    machine; see scripts/sign-index.sh)
#   catalog.tar.gz   the blueprints/ tree, which keeps check file by file
#                    against the index
#   blueprints/      the same files, unpacked, for people browsing
#
# Keeps fetch these from https://keepcmd.com/blueprints/ (published from the
# Keep Cmd site's repo), verify the signature against the catalog keys
# compiled into keepcmd, and refuse an index whose catalog_version is older
# than the one they have.
#
# Usage:
#   scripts/release.sh <catalog_version>        e.g. 2026.10.08 (or 2026.10.08.1)
#
# DIST=<dir> writes somewhere other than dist/.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/release.sh <catalog_version>" >&2
  exit 1
fi

CATALOG_VERSION="$1"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${DIST:-$REPO_ROOT/dist}"

cd "$REPO_ROOT"
rm -rf "$DIST"
mkdir -p "$DIST"

echo "==> validating and building the index"
python3 -I scripts/build-index.py "$CATALOG_VERSION" "$DIST/index.json"

echo "==> building catalog.tar.gz"
# Reproducible: fixed mtime and owner, sorted names, and gzip without a
# timestamp, so the same tree gives the same bytes. (GNU tar; on macOS,
# brew install gnu-tar and put gtar first as tar.)
tar --sort=name \
    --mtime='UTC 2020-01-01' \
    --owner=0 --group=0 --numeric-owner \
    --format=gnu \
    -cf - blueprints | gzip -n -9 > "$DIST/catalog.tar.gz"
cp -R blueprints "$DIST/blueprints"

echo "==> signing"
KEY="${SOURCECMD_CATALOG_SIGNING_KEY:-}"
if [[ -n "$KEY" && -f "$KEY" ]]; then
  scripts/sign-index.sh "$DIST/index.json" "$KEY" "$DIST/index.json.sig"
else
  echo "    not signing here (SOURCECMD_CATALOG_SIGNING_KEY isn't set to a key on this machine)."
  echo "    Sign on the machine holding the key, then put index.json.sig beside index.json:"
  echo "        scripts/sign-index.sh index.json <key> index.json.sig"
  echo "    Keeps refuse an unsigned index."
fi

echo
ls -la "$DIST"
