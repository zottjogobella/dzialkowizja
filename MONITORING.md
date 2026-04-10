# Unified Production Monitoring

Central health check runs from this server (dzialkowizja, `45.137.213.188`) every hour via cron.
Sends a single Lark notification with per-service status + daily revenue stats.

## Setup

- **Script**: `/home/deploy/scripts/healthcheck.sh`
- **Cron**: `0 * * * * /home/deploy/scripts/healthcheck.sh` (as `deploy` user)
- **Lark webhook**: Bot "zk notifications" in Lark group "ZnajdzKsiege Notifications"
- **IP whitelist** on Lark bot: `66.29.157.198` (znajdzksiege), `45.137.213.188` (dzialkowizja)

## Services Checked

| Service | Check Type | What It Proves |
|---------|-----------|----------------|
| znajdzksiege.online | Login (POST /api/v1/auth/login/) | Django + DB |
| ksiegiwieczyste.io | Login (POST /api/auth/login) | Express + DB |
| gruntomat | Auth endpoint (GET /api/v1/queries → 401) | FastAPI + middleware |
| ekw.plus | Laravel login with CSRF (POST /logowanie) | Laravel + DB |
| bemben bigboy | TCP port 5432 on 51.75.52.102 | PostgreSQL up |
| bemben bigboy_2 | TCP port 5432 on 145.239.2.73 | PostgreSQL up |

## Healthcheck Users

| Service | Email | Password |
|---------|-------|----------|
| znajdzksiege.online | healthcheck@znajdzksiege.online | hc-zk-2026 |
| ksiegiwieczyste.io | healthcheck@ksiegiwieczyste.io | hc-kw-2026 |
| ekw.plus | topeppero420@gmail.com | password |

## Status Colors

- **Green (Healthy)**: Response < 3 seconds
- **Orange (SLOW)**: Response >= 3 seconds
- **Red (DOWN)**: Unreachable or unexpected HTTP status

## Revenue Stats

Fetched via API keys from znajdzksiege and ksiegiwieczyste daily-stats endpoints.
Shows today's revenue + transaction count and yesterday's revenue.

## Lark Payment Notifications

Separate from the health check — znajdzksiege.online also sends real-time Lark cards for:
- Payment success (green, anonymized: amount + method only)
- Payment failure (red, with error details in collapsible panel)
- Webhook errors (red, with URGENT note)

Code: `znajdz_ksiege/lark_service.py` and `znajdz_ksiege/lark_cards.py`
Config: `LARK_WEBHOOK_URL`, `LARK_WEBHOOK_SECRET`, `LARK_NOTIFICATIONS_ENABLED` in `.env`

## SSH Access

- dzialkowizja: `ssh dzialkowizja` (deploy@45.137.213.188, key: ~/.ssh/id_ed25519)
- znajdzksiege: `ssh znajdzksiege` (gniew@znajdzksiege.online, key: ~/.ssh/id_ed25519_gitlab_zott)
- gruntomat: `ssh gruntomat` (ubuntu@145.239.2.73, key: ~/.ssh/geoportal_server)
