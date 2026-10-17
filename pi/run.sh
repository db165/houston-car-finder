#!/usr/bin/env bash
## one collection cycle on the pi: update code, crawl, push the snapshot to the "collected" branch
set -euo pipefail

repo="$HOME/houston-car-finder"
out="$HOME/carfinder-out"

# pick up any changes made on github (config tweaks, new sources)
git -C "$repo" pull -q --ff-only origin main || echo "git pull failed, running the code already here"

cd "$repo"
python3 -m carfinder.collect --config config.yml --out "$out"

# push as a single fresh commit so the branch never grows
cd "$out"
rm -rf .git
git init -q
git checkout -q -b collected
git add -A
git -c user.name="carfinder-pi" -c user.email="carfinder-pi@users.noreply.github.com" commit -q -m "collect $(date -u +%FT%TZ)"
git push -q -f git@github-carfinder:db165/houston-car-finder.git collected
echo "pushed snapshot"
