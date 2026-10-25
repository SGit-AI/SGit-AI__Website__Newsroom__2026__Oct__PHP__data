#!/usr/bin/env bash
# Release the data: take in dev, gate, bump, publish, gate again, commit, push. In that order, every time.
# Usage: tools/release.sh "<one sentence: what changed and why>" [patch|minor|major]
#   patch: the same shapes, new or corrected values (a new export, a new review)
#   minor: a new file, or a schema widened (a new key); tools/schema.py --again first
#   major: a key removed or renamed; consumers move to it on purpose, the old versions stay published
# Never --no-verify, never a force-push, never main. A published version is never changed: this only adds one.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
MSG="${1:?release message required}"; PART="${2:-patch}"
BRANCH="${RELEASE_BRANCH:-dev}"
# 0. take in what landed meanwhile; files/ is the only place two writers can collide, so a conflict stops the release
git fetch -q origin "$BRANCH" 2>/dev/null || true
if git rev-parse -q --verify "origin/$BRANCH" >/dev/null && ! git merge-base --is-ancestor "origin/$BRANCH" HEAD; then
  if ! git merge -q --ff-only "origin/$BRANCH" 2>/dev/null; then
    echo "release stopped: origin/$BRANCH has commits this clone does not; commit or stash your files/ change, merge origin/$BRANCH by hand, and run this again"
    exit 3
  fi
fi
python3 tools/gate.py >/dev/null || { python3 tools/gate.py; echo "release stopped: the gate fails before the release"; exit 1; }
OLD="$(cat VERSION)"; IFS=. read -r MA MI PA <<< "$OLD"
if [ -d "v/$OLD" ]; then
  case "$PART" in major) MA=$((MA+1)); MI=0; PA=0;; minor) MI=$((MI+1)); PA=0;; *) PA=$((PA+1));; esac
fi
NEW="$MA.$MI.$PA"; echo "$NEW" > VERSION
python3 tools/publish.py
python3 tools/gate.py
git add -A
if git diff --cached | grep -E -n 'sgit_private_(vault|read)_[0-9a-f]{12,}|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}' ; then
  echo "tripwire: credential shape in the staged diff; release aborted"; exit 1
fi
if [ -n "${RELEASE_TRAILER:-}" ]; then git commit -q -m "v$NEW: $MSG" -m "$RELEASE_TRAILER"; else git commit -q -m "v$NEW: $MSG"; fi
git push -q -u origin "HEAD:$BRANCH"
echo "pushed v$NEW to $BRANCH"
