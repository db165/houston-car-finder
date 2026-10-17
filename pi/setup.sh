#!/usr/bin/env bash
## one-time raspberry pi setup for the car finder
## run with:  curl -fsSL https://raw.githubusercontent.com/db165/houston-car-finder/main/pi/setup.sh | bash
set -euo pipefail

repo="$HOME/houston-car-finder"
key="$HOME/.ssh/carfinder_deploy"

echo "== 1/5 installing packages (a few minutes on a pi 3)"
sudo apt-get update -qq
sudo apt-get install -y -qq git python3 python3-requests python3-bs4 python3-yaml > /dev/null

echo "== 2/5 downloading the code"
if [ -d "$repo/.git" ]; then
  git -C "$repo" pull -q --ff-only origin main
else
  git clone -q https://github.com/db165/houston-car-finder.git "$repo"
fi

echo "== 3/5 creating a key that can push to this one repo only"
mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
[ -f "$key" ] || ssh-keygen -q -t ed25519 -N "" -C "carfinder-pi" -f "$key"
if ! grep -q "Host github-carfinder" "$HOME/.ssh/config" 2>/dev/null; then
  cat >> "$HOME/.ssh/config" <<EOF
Host github-carfinder
  HostName github.com
  User git
  IdentityFile $key
  IdentitiesOnly yes
EOF
  chmod 600 "$HOME/.ssh/config"
fi
ssh-keyscan -q github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null

keyWorks() { local out; out=$(ssh -o BatchMode=yes -T git@github-carfinder 2>&1 || true); [[ "$out" == *"successfully authenticated"* ]]; }
until keyWorks; do
  echo
  echo "Add this key on GitHub: repo -> Settings -> Deploy keys -> Add deploy key"
  echo "Title: raspberry pi    Key: (the line below)    and CHECK 'Allow write access'"
  echo
  cat "$key.pub"
  echo
  read -r -p "Press Enter once it's saved... " < /dev/tty
done
echo "GitHub accepted the key."

echo "== 4/5 scheduling a run every 10 minutes (survives reboots and power cuts)"
sudo tee /etc/systemd/system/carfinder.service > /dev/null <<EOF
[Unit]
Description=car finder collector
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$USER
ExecStart=/bin/bash $repo/pi/run.sh
TimeoutStartSec=15min
EOF
sudo tee /etc/systemd/system/carfinder.timer > /dev/null <<EOF
[Unit]
Description=run the car finder collector every 10 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now carfinder.timer > /dev/null

echo "== 5/5 first run (takes a few minutes, watch the per-site status at the end)"
# run it as the scheduled service (systemd never runs two at once), then show how each site did
sudo systemctl start carfinder.service || true
journalctl -u carfinder -n 25 --no-pager -o cat

echo
echo "All set. Useful commands:"
echo "  journalctl -u carfinder -n 40     # last run's log"
echo "  systemctl list-timers carfinder   # when it runs next"
