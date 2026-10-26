#!/usr/bin/env bash
# Keep the collected data on a separate branch so daily commits never touch the code.
#   automation/data-branch.sh pull <dir>            clone the data branch (create it if missing)
#   automation/data-branch.sh push <dir> <message>  commit and push changes, if any
# Needs GITHUB_TOKEN and GITHUB_REPOSITORY (both set by GitHub Actions), or DATA_REMOTE.
set -euo pipefail

cmd=${1:?pull|push}
dir=${2:?directory}
branch=${DATA_BRANCH:-market-data}
# DATA_REMOTE overrides the remote (used to test this script against a local repo).
remote=${DATA_REMOTE:-"https://x-access-token:${GITHUB_TOKEN:?}@github.com/${GITHUB_REPOSITORY:?}.git"}

case "$cmd" in
  pull)
    if git ls-remote --exit-code --heads "$remote" "$branch" >/dev/null 2>&1; then
      git clone --quiet --depth 1 --branch "$branch" "$remote" "$dir"
    else
      echo "Branch $branch does not exist yet; starting it."
      git init --quiet -b "$branch" "$dir"
      git -C "$dir" remote add origin "$remote"
      cat > "$dir/README.md" <<'MD'
# market-data

Written by the scheduled GitHub Actions workflows; do not edit by hand.

- `daily/<source>/<SYMBOL>.csv`: daily bars, merged every weekday after the close
- `reports/<name>.json`: weekly walk-forward research reports

Analysis only. Nothing here is an order or investment advice.
MD
    fi
    ;;
  push)
    msg=${3:-"Update market data"}
    if [ ! -d "$dir/.git" ]; then echo "No data checkout at $dir; nothing to push."; exit 0; fi
    git -C "$dir" config user.name "github-actions[bot]"
    git -C "$dir" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git -C "$dir" add -A
    if git -C "$dir" diff --cached --quiet; then echo "No changes to push."; exit 0; fi
    git -C "$dir" commit --quiet -m "$msg"
    for attempt in 1 2 3 4; do
      if git -C "$dir" push --quiet origin "HEAD:$branch"; then exit 0; fi
      sleep $((2 ** attempt))
      git -C "$dir" pull --quiet --rebase origin "$branch" || true
    done
    echo "Push failed after retries." >&2
    exit 1
    ;;
  *)
    echo "unknown command: $cmd" >&2
    exit 2
    ;;
esac
