━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Phase 0 Deployment Runbook — Oracle Cloud
ID:          OPS-20260926-001
Author:      Nakula (DevOps)
Owner:       Atharva
Date:        2026-09-26
Version:     v1.0
Status:      Active
References:  IMP-20260923-001, ARCH-20260923-001, SEC-20260925-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Phase 0 Deployment Runbook — Oracle Cloud Free Tier

---

## Prerequisites

| Item | Requirement |
|---|---|
| Instance | Oracle Cloud Always Free — VM.Standard.A1.Flex (Ampere ARM) or E2.1.Micro (AMD) |
| OS | Ubuntu 22.04 LTS |
| Domain | A domain pointed at the instance's public IP (A record) |
| Ports | 22 (SSH), 80 (HTTP), 443 (HTTPS) open in OCI Security List and OS firewall |
| Local machine | Git, SSH key added to Oracle Cloud |

---

## Step 1 — Provision the Oracle Cloud Instance

1. Log into [console.oracle.com](https://console.oracle.com).
2. Create a Compute Instance:
   - **Shape:** VM.Standard.A1.Flex (4 OCPU / 24 GB RAM — free tier) or E2.1.Micro
   - **Image:** Canonical Ubuntu 22.04
   - **SSH key:** upload your public key
3. Note the public IP address.
4. In **Networking → VCN → Security Lists**, add ingress rules for:
   - TCP port 80 from 0.0.0.0/0
   - TCP port 443 from 0.0.0.0/0

---

## Step 2 — Point a Domain at the Instance

Create an A record:

```
Type: A
Name: viveka.yourdomain.com  (or @)
Value: <instance public IP>
TTL: 300
```

Wait for DNS propagation before proceeding (check with `dig viveka.yourdomain.com`).

---

## Step 3 — Bootstrap the Server

SSH into the instance and run the bootstrap script as root:

```bash
ssh ubuntu@<instance-ip>
sudo -i
git clone <your-repo-url> /tmp/viveka-deploy
bash /tmp/viveka-deploy/deploy/bootstrap.sh
```

The script will:
- Set timezone to IST (Asia/Kolkata)
- Install PostgreSQL 15, Python 3.11, Caddy
- Create the `viveka` service account
- Create the `/srv/viveka`, `/var/log/viveka`, `/data/documents` directories
- Create the PostgreSQL `viveka` database and user
- **Print the generated PostgreSQL password once — save it immediately**
- Open ports 80 and 443 in iptables

---

## Step 4 — Deploy Application Code

```bash
# On the server (as root or ubuntu)
cd /srv/viveka
git clone <your-repo-url> repo
cp -r repo/backend /srv/viveka/backend
cp -r repo/deploy  /srv/viveka/deploy
chown -R viveka:viveka /srv/viveka
```

---

## Step 5 — Create the Environment File

```bash
cp /srv/viveka/deploy/.env.oracle.template /srv/viveka/.env
chmod 600 /srv/viveka/.env
chown viveka:viveka /srv/viveka/.env
```

Edit `/srv/viveka/.env` and fill in every `CHANGE_ME` value:

| Variable | How to generate |
|---|---|
| `DATABASE_URL` | Use the PostgreSQL password printed in Step 3 |
| `SECRET_KEY` | `python3.11 -c "import secrets; print(secrets.token_hex(32))"` |
| `ALLOWED_EMAILS` | Your email address |

**Verify `.env` is not tracked by git:**
```bash
git ls-files /srv/viveka/backend/.env
```
Must return empty. (`.gitignore` covers this — SR-AUTH-011.)

---

## Step 6 — Set Up Python Virtual Environment

```bash
cd /srv/viveka
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e backend/
deactivate
chown -R viveka:viveka /srv/viveka/venv
```

---

## Step 7 — Run Database Migrations

```bash
cd /srv/viveka/backend
sudo -u viveka /srv/viveka/venv/bin/alembic upgrade head
```

Verify 11 tables exist:

```bash
sudo -u postgres psql -d viveka -c "\dt"
```

Expected tables: `users`, `user_sessions`, `companies`, `sectors`, `sector_classifications`,
`prices`, `documents`, `reports`, `watchlist_items`, `trading_calendar`, `alembic_version`.

---

## Step 8 — Configure and Start Caddy

```bash
# Edit the Caddyfile — replace REPLACE_WITH_YOUR_DOMAIN
cp /srv/viveka/deploy/Caddyfile /etc/caddy/Caddyfile
nano /etc/caddy/Caddyfile   # replace REPLACE_WITH_YOUR_DOMAIN

# Validate config
caddy validate --config /etc/caddy/Caddyfile

# Start Caddy (it provisions TLS automatically)
systemctl enable caddy
systemctl start caddy
systemctl status caddy
```

---

## Step 9 — Install and Start the API Service

```bash
cp /srv/viveka/deploy/viveka-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable viveka-api
systemctl start viveka-api
systemctl status viveka-api
```

---

## Step 10 — Smoke Test

```bash
# Health check via HTTPS (TLS must be provisioned by now — wait ~30s after Step 8)
curl -s https://viveka.yourdomain.com/api/v1/auth/me
# Expected: 401 {"detail":"Not authenticated"} — service is up, auth is working
```

**Verify HSTS header (SR-AUTH-012):**
```bash
curl -sI https://viveka.yourdomain.com/api/v1/auth/me | grep -i strict-transport-security
# Expected: strict-transport-security: max-age=31536000; includeSubDomains
```

**Verify security headers (SR-AUTH-012):**
```bash
curl -sI https://viveka.yourdomain.com/api/v1/auth/me | grep -iE "x-content-type|x-frame|referrer"
# Expected: x-content-type-options: nosniff
#           x-frame-options: DENY
#           referrer-policy: strict-origin-when-cross-origin
```

---

## Step 11 — SR-AUTH-011 Git Verification

Now that git is initialised on the server, verify `.env` is not tracked:

```bash
cd /srv/viveka/backend
git ls-files | grep -E "^\.env$"
```
Must return empty.

---

## Operational Notes

### Logs

```bash
# API logs
tail -f /var/log/viveka/api.log

# Caddy logs
journalctl -u caddy -f

# PostgreSQL logs
tail -f /var/log/postgresql/postgresql-15-main.log
```

### Service management

```bash
# Restart API after code update
sudo systemctl restart viveka-api

# Reload Caddy config without downtime
sudo systemctl reload caddy
```

### Code updates

```bash
cd /srv/viveka/repo
git pull
cp -r backend /srv/viveka/
chown -R viveka:viveka /srv/viveka/backend
sudo -u viveka /srv/viveka/venv/bin/alembic upgrade head
sudo systemctl restart viveka-api
```

### Rollback

```bash
cd /srv/viveka/repo
git checkout <previous-sha>
cp -r backend /srv/viveka/
chown -R viveka:viveka /srv/viveka/backend
# Alembic downgrade only if the migration was destructive — check first:
# sudo -u viveka /srv/viveka/venv/bin/alembic downgrade -1
sudo systemctl restart viveka-api
```

---

## Deferred Items

| Item | When | Owner |
|---|---|---|
| Next.js frontend (uncomment reverse_proxy in Caddyfile) | Phase 1 | Nakula + Arjun |
| APScheduler PostgreSQL job store config | Phase 1 | Nakula + Bhima |
| LLM cost ceiling enforcement (ANTHROPIC_API_KEY) | Phase 4 | Nakula |
| Automated log rotation | Before Phase 1 | Nakula |
| Certificate expiry alerting | Before Phase 1 | Nakula |

---

*OPS-20260926-001 · v1.0 · Atharva · Active · 2026-09-26*
