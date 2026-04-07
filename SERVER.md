# Server Setup

**IP:** 45.137.213.188  
**OS:** Ubuntu 24.04 LTS  
**SSH:** `ssh -i ~/.ssh/id_ed25519 deploy@45.137.213.188`

## Access

- Root login disabled
- Password auth disabled — SSH key only
- User `deploy` with passwordless sudo

## Firewall (UFW)

- Port 22 — SSH
- Port 80 — HTTP
- Port 443 — HTTPS
- Everything else denied

## Rate Limiting (Nginx)

| Zone | Rate | Burst | Purpose |
|------|------|-------|---------|
| `general` | 10 req/s per IP | 20 | All pages |
| `api` | 30 req/s per IP | 50 | API endpoints |
| `login` | 3 req/min per IP | 5 | Auth endpoints |

Over-limit requests get HTTP 429. Connection limit: 50 per IP.

## Security Headers

- `X-Frame-Options: SAMEORIGIN` — prevents clickjacking
- `X-Content-Type-Options: nosniff` — prevents MIME sniffing
- `X-XSS-Protection: 1; mode=block` — XSS filter
- `Referrer-Policy: strict-origin-when-cross-origin` — limits referrer leaks
- `Permissions-Policy` — blocks camera, microphone, geolocation

## Blocked Paths

Nginx returns 404 for: `.env`, `.git`, `.sql`, `.log`, `.bak`, `.config`, `.sh`, and all hidden files.

## Services

- **Nginx 1.24** — reverse proxy with gzip, security headers, rate limiting
- **Docker 29.4 + Compose 5.1** — app containers
- **Fail2Ban** — brute-force protection on SSH
- **Unattended-upgrades** — automatic security patches

## TODO (when app is deployed)

- [ ] Add domain + SSL via Let's Encrypt
- [ ] Uncomment Nginx reverse proxy rules for `/api/` and `/api/auth/`
- [ ] Add CORS headers for the frontend domain
- [ ] Set up Docker Compose for the app
