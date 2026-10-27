#!/usr/bin/env bash
# Release the data: take in dev, gate, commit, push. That is all. CI owns the version
# (https://sharness.ai/articles/ci-owns-the-version.html): after its own gate passes, CI writes VERSION (the newest tag
# plus one on the last number), commits it as GitHub Actions with this commit's subject after the number, tags it and
# deploys it. So two writers releasing a minute apart never fight over a number, and this script never touches VERSION
# (a pushed commit that changes it fails CI's guard). Your next release takes CI's commit in first, as it does any other.
# Usage: tools/release.sh "<one sentence: what changed and why>"   (RELEASE_TRAILER: Agent: <you>, and the rest)
# Never --no-verify, never a force-push, never main.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
MSG="${1:?release message required}"
BRANCH="${RELEASE_BRANCH:-dev}"
gate() { python3 tools/gate.py; }
take_in() {
  git fetch -q origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  if ! git merge-base --is-ancestor "origin/$BRANCH" HEAD; then
    git merge -q --ff-only "origin/$BRANCH" 2>/dev/null || {
      echo "release stopped: your change and one that landed meanwhile touch the same file; commit or stash yours, merge origin/$BRANCH by hand, run this again"; exit 3; }
  fi
}
take_in
gate || { echo "release stopped: the gate fails"; exit 1; }
git add -A
if git diff --cached | grep -E -n 'sgit_private_(vault|read)_[0-9a-f]{12,}|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|\bsk-(or-v1-|proj-|ant-[a-z0-9]+-)?[A-Za-z0-9_]{32,}' | head -3; then
  echo "release stopped: a credential shape in the change"; git reset -q; exit 2
fi
if git diff --cached --name-only | grep -qx VERSION; then
  echo "release stopped: VERSION is written by CI only (git checkout -- VERSION)"; git reset -q; exit 2
fi
if git diff --cached --quiet; then echo "nothing to release"; exit 0; fi
for attempt in 1 2 3 4 5; do
  if [ -n "${RELEASE_TRAILER:-}" ]; then git commit -q -m "$MSG" -m "$RELEASE_TRAILER"; else git commit -q -m "$MSG"; fi
  if git push -q origin "HEAD:$BRANCH" 2>/dev/null; then
    echo "pushed to $BRANCH; CI gates it again, tags the next version and deploys"; exit 0
  fi
  echo "push rejected (someone released meanwhile): taking it in ($attempt of 5)"
  git reset -q --soft HEAD~1; git reset -q
  take_in
  gate || { echo "release stopped: the gate fails with what landed meanwhile"; exit 1; }
  git add -A
done
echo "release stopped: five tries, five releases by others in between; run this again"; exit 3
