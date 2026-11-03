#!/usr/bin/env bash
# Execute Python code in a running marimo notebook session (code mode).
#
# Usage:
#   execute-code.sh --url http://127.0.0.1:2718 < script.py
#   echo 'print(1+1)' | execute-code.sh --url http://127.0.0.1:2718
#
# Options:
#   --url URL          marimo server URL (default: http://127.0.0.1:2718)
#   --session ID       session id (auto-detected when only one is open)
#   --token-file PATH  token file, passed through to `marimo pair execute`
#
# Code is read from stdin unless --code-file is given.

set -euo pipefail

URL="http://127.0.0.1:2718"
SESSION=""
TOKEN_ARGS=()
CODE_FILE="-"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --token-file) TOKEN_ARGS=(--token-file "$2"); shift 2 ;;
    --code-file) CODE_FILE="$2"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$SESSION" ]]; then
  SESSION="$(uv run marimo pair notebook list --url "$URL" "${TOKEN_ARGS[@]}" \
    | python3 -c 'import json,sys; ns=json.load(sys.stdin)["notebooks"]; s=[x["session_id"] for n in ns for x in n["sessions"]]; print(s[0] if len(s)==1 else "")')"
  if [[ -z "$SESSION" ]]; then
    echo "could not auto-detect a single session at $URL; pass --session" >&2
    exit 1
  fi
fi

exec uv run marimo pair execute \
  --url "$URL" \
  --session "$SESSION" \
  --code-file "$CODE_FILE" \
  "${TOKEN_ARGS[@]}"
