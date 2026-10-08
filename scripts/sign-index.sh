#!/usr/bin/env bash
#
# Sign a built index.json, producing the detached index.json.sig that keeps
# verify before storing anything from this catalog.
#
# RUN THIS WHERE THE CATALOG SIGNING KEY LIVES. It is the same key set the
# plugin catalog is signed with (D-164): the public halves are compiled into
# every keepcmd binary (trustedCatalogKeys), so anyone holding a private half
# can publish blueprints every keep trusts, pre-ticked asks included. Never
# copy it to a server, CI or this repo, and never paste it anywhere.
#
# Usage:
#   scripts/sign-index.sh <index.json> [private_key] [output.sig]
#
# private_key defaults to $SOURCECMD_CATALOG_SIGNING_KEY.

set -euo pipefail

INDEX="${1:-}"
KEY="${2:-${SOURCECMD_CATALOG_SIGNING_KEY:-}}"
SIG="${3:-${INDEX}.sig}"

if [[ -z "$INDEX" || -z "$KEY" ]]; then
  echo "Usage: scripts/sign-index.sh <index.json> <private_key> [output.sig]" >&2
  exit 1
fi
[[ -f "$INDEX" ]] || { echo "error: no such file: $INDEX" >&2; exit 1; }
[[ -f "$KEY" ]] || { echo "error: signing key not found: $KEY" >&2; exit 1; }

find_openssl() {
  for candidate in \
      "${OPENSSL:-}" \
      /opt/homebrew/opt/openssl@3/bin/openssl \
      /usr/local/opt/openssl@3/bin/openssl \
      "$(command -v openssl 2>/dev/null || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" genpkey -algorithm ED25519 -out /dev/null 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! SSL="$(find_openssl)"; then
  echo "error: no OpenSSL with Ed25519 support found (macOS LibreSSL can't do this): brew install openssl@3" >&2
  exit 1
fi

# -rawin signs the message itself, as Ed25519 needs and Go's ed25519.Verify
# expects.
"$SSL" pkeyutl -sign -inkey "$KEY" -rawin -in "$INDEX" -out "$SIG"

SIZE=$(wc -c < "$SIG" | tr -d ' ')
if [[ "$SIZE" != "64" ]]; then
  echo "error: signature is $SIZE bytes, expected 64. Wrong key type?" >&2
  rm -f "$SIG"
  exit 1
fi

PUB_TMP="$(mktemp)"
trap 'rm -f "$PUB_TMP"' EXIT
"$SSL" pkey -in "$KEY" -pubout -out "$PUB_TMP"
if ! "$SSL" pkeyutl -verify -pubin -inkey "$PUB_TMP" -rawin -in "$INDEX" -sigfile "$SIG" >/dev/null 2>&1; then
  echo "error: the signature just written does not verify. Refusing to ship it." >&2
  rm -f "$SIG"
  exit 1
fi

HEX="$("$SSL" pkey -pubin -in "$PUB_TMP" -outform DER | tail -c 32 | xxd -p -c 64)"
echo "wrote $SIG (64 bytes, verified)"
echo "signed by public key: $HEX"
echo "(that public key must be in keepcmd's trustedCatalogKeys, or every keep refuses this index)"
