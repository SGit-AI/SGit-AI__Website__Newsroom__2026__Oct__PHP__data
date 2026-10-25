#!/usr/bin/env bash
# Release the data: take in dev, gate, bump, publish, gate again, commit, push. In that order, every time.
# Usage: tools/release.sh "<one sentence: what changed and why>"
# The first release was 0.1.0; every release after it adds one to the last number (0.1.1, 0.1.2, ...), whatever it
# changes (the editor, 25 October 2026). A change of shape (a new file, a key added or removed) is said in the message,
# and its schema is rewritten in the same release (tools/schema.py --again); consumers pin the version they read.
# Never --no-verify, never a force-push, never main. A published version is never changed: this only adds one.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
MSG="${1:?release message required}"
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
if python3 tools/publish.py --same-as "$OLD"; then
  NEW="$OLD"; echo "nothing new to publish: v$OLD holds these files already"   # a change to the tools still commits
else
  if [ -d "v/$OLD" ]; then PA=$((PA+1)); fi
  NEW="$MA.$MI.$PA"; echo "$NEW" > VERSION
  python3 tools/publish.py
  python3 tools/gate.py
fi
git add -A
if git diff --cached | grep -E -n 'sgit_private_(vault|read)_[0-9a-f]{12,}|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|\bsk-(or-v1-|proj-|ant-[a-z0-9]+-)?[A-Za-z0-9_]{32,}' ; then
  echo "tripwire: credential shape in the staged diff; release aborted"; exit 1
fi
if [ -n "${RELEASE_TRAILER:-}" ]; then git commit -q -m "v$NEW: $MSG" -m "$RELEASE_TRAILER"; else git commit -q -m "v$NEW: $MSG"; fi
git push -q -u origin "HEAD:$BRANCH"
echo "pushed v$NEW to $BRANCH"
