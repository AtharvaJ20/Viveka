#!/usr/bin/env bash
# Phase 0 Oracle Cloud Ubuntu 22.04 bootstrap
# Run as root on a fresh instance. Idempotent on re-run.

set -euo pipefail

# ── Timezone (IST) ────────────────────────────────────────────────────────────
timedatectl set-timezone Asia/Kolkata
echo "Timezone: $(timedatectl show --property=Timezone --value)"

# ── System update ─────────────────────────────────────────────────────────────
apt-get update -y
apt-get upgrade -y
apt-get install -y \
    curl wget gnupg2 software-properties-common \
    apt-transport-https ca-certificates lsb-release \
    build-essential libpq-dev

# ── PostgreSQL 15 ─────────────────────────────────────────────────────────────
if ! command -v psql &>/dev/null; then
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
    echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
    apt-get update -y
    apt-get install -y postgresql-15
fi
systemctl enable postgresql
systemctl start postgresql

# ── Python 3.11 ───────────────────────────────────────────────────────────────
if ! python3.11 --version &>/dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -y
    apt-get install -y python3.11 python3.11-venv python3.11-dev
fi

# ── Caddy ─────────────────────────────────────────────────────────────────────
if ! command -v caddy &>/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /etc/apt/trusted.gpg.d/caddy-stable.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
fi

# ── Service account ───────────────────────────────────────────────────────────
id viveka &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin viveka

# ── Directory layout ──────────────────────────────────────────────────────────
install -d -o viveka -g viveka /srv/viveka
install -d -o viveka -g viveka /var/log/viveka
install -d -o viveka -g viveka /data/documents

# ── PostgreSQL: database + user ───────────────────────────────────────────────
# Run only when the viveka database does not yet exist.
if ! sudo -u postgres psql -lqt | cut -d\| -f1 | grep -qw viveka; then
    DB_PASS=$(python3.11 -c "import secrets; print(secrets.token_hex(24))")
    sudo -u postgres psql <<SQL
CREATE USER viveka WITH PASSWORD '${DB_PASS}';
CREATE DATABASE viveka OWNER viveka ENCODING 'UTF8' LC_COLLATE 'en_US.UTF-8' LC_CTYPE 'en_US.UTF-8' TEMPLATE template0;
GRANT ALL PRIVILEGES ON DATABASE viveka TO viveka;
SQL
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  SAVE THIS — PostgreSQL password generated once only:       ║"
    echo "║  DB_PASS=${DB_PASS}  ║"
    echo "║  Set DATABASE_URL in /srv/viveka/.env                       ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
else
    echo "PostgreSQL viveka database already exists — skipping creation."
fi

# Ensure PostgreSQL only listens on localhost (default in pg_hba.conf, explicit here)
grep -q "127.0.0.1/32.*viveka" /etc/postgresql/15/main/pg_hba.conf \
    || echo "host    viveka          viveka          127.0.0.1/32            scram-sha-256" \
        >> /etc/postgresql/15/main/pg_hba.conf
systemctl reload postgresql

# ── Oracle Cloud firewall: open HTTP + HTTPS ──────────────────────────────────
# The instance's iptables-based firewall blocks ports 80/443 by default on OCI.
# Also open them in the OCI Console > Networking > Security Lists (manual step).
iptables -C INPUT -p tcp --dport 80  -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 80  -j ACCEPT
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 443 -j ACCEPT
# Persist across reboots (Ubuntu 22.04)
apt-get install -y iptables-persistent
netfilter-persistent save

echo ""
echo "Bootstrap complete. Continue with the runbook: deploy/runbook.md"
