#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu VM (written for Oracle Cloud's Always Free
# Ampere A1 shape running Ubuntu 24.04).
#
#   bash deploy/bootstrap.sh
#
# Run as a normal user with sudo — not as root, because the docker group is
# granted to "$USER".
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as a normal user with sudo, not as root." >&2
  exit 1
fi

echo "==> installing Docker and the compose plugin"
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg ufw

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# So compose does not need sudo every time. Takes effect on next login.
sudo usermod -aG docker "$USER"

echo "==> firewall"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose

# Oracle's Ubuntu images ship an iptables ruleset that rejects everything except
# SSH, and it is applied on boot independently of ufw. Opening the ports in the
# web console is therefore not enough on its own: without the rules below,
# nginx is reachable locally and unreachable from the internet, which looks
# exactly like a broken TLS setup.
if grep -qi oracle /etc/cloud/cloud.cfg 2>/dev/null || [ -d /etc/iptables ]; then
  echo "==> Oracle image detected: allowing 80/443 through its own iptables rules"
  for port in 80 443; do
    sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
      || sudo iptables -I INPUT 5 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null; then
    sudo netfilter-persistent save
  fi
fi

cat <<'EOF'

Done. Two more things before `docker compose` will work end to end:

  1. Log out and back in (or run `newgrp docker`) so the docker group applies.
  2. Open ingress for TCP 80 and 443 in the OCI security list / NSG attached to
     this instance's subnet. That is separate from ufw and is the step most
     often missed.

Then:  cp deploy/.env.example deploy/.env   # fill it in, then
       bash deploy/init-letsencrypt.sh
       cd deploy && docker compose --env-file .env up -d --build
EOF
