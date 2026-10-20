#!/bin/sh
# 병렬 트랙용 git worktree를 만든다/지운다.
#   sh scripts/worktree.sh <track>           → ../Day-0_zaeho.worktrees/<track> 에 track/<track> 브랜치
#   sh scripts/worktree.sh --remove <track>
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WT_DIR="$ROOT/../$(basename "$ROOT").worktrees"
if [ "$1" = "--remove" ]; then
  git -C "$ROOT" worktree remove "$WT_DIR/$2"
  echo "removed $WT_DIR/$2 (브랜치 track/$2 는 남김)"
  exit 0
fi
[ -n "$1" ] || { echo "usage: $0 [--remove] <track>"; exit 1; }
mkdir -p "$WT_DIR"
git -C "$ROOT" worktree add -b "track/$1" "$WT_DIR/$1" main
echo "$WT_DIR/$1  (branch track/$1)"
