#!/usr/bin/env bash
# Run this once on a fresh Ubuntu 24.04 VPS as root
set -euo pipefail

echo "==> Updating packages"
apt-get update && apt-get upgrade -y

echo "==> Installing Docker"
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
usermod -aG docker "$SUDO_USER" 2>/dev/null || true

echo "==> Installing Docker Compose plugin"
apt-get install -y docker-compose-plugin

echo "==> Installing Fail2Ban & UFW"
apt-get install -y fail2ban ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
systemctl enable --now fail2ban

echo "==> Hardening SSH (disable password auth)"
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd

echo ""
echo "✅ VPS ready."
echo "   1. Copy your project: scp -r algo-platform/ root@<IP>:/opt/algo-platform"
echo "   2. cd /opt/algo-platform && cp .env.example .env && nano .env"
echo "   3. docker compose up -d"
