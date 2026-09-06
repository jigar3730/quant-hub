# Quant Hub Setup Guide

**This is the only installation path.** Do not invent a shortcut.

**Do not do these three things** (they start an empty or colliding stack):

1. Do not run `cp .env.example .env` then `docker compose up`.
2. Do not run bare `docker compose ps` / `up` against `docker-compose.yml` alone (it has **no volumes**). Always use `./scripts/run_env.sh {dev|stage|prod}`.
3. Port **5002** + `/mnt/fast/quant-data` is strictly **prod**, not every environment. Dev uses Docker volumes and `quant-hub-dev`. Stage uses port **5003** and `/mnt/fast/quant-data-stage/`.

**Who this is for:** Someone who has never used Docker, `.env` files, or a trading research stack.  
**What you will have at the end:** A website (the dashboard) and a database, started as **dev** (practice) or **prod** (live data).  
**Time:** about 20–40 minutes the first time.

Quant Hub does **not** buy or sell stocks. If a step fails, stop and use [Common troubleshooting](#8-common-troubleshooting).

---

## Which environment should I start?

| Environment | Use it when | Data lives | Safe to experiment? |
|-------------|-------------|------------|---------------------|
| **dev** | First time, learning, changing code | Docker’s own disks (not your live data) | Yes |
| **stage** | Dress rehearsal before prod | `/mnt/fast/quant-data-stage/` | Yes, separate from prod |
| **prod** | The real homelab stack | `/mnt/fast/quant-data/` | No — this is the live database |

**Start with `dev`.** Only use `prod` if you already have `/mnt/fast/quant-data` and want the existing live stack.

---

## 1. Prerequisites checklist

You need a computer that can run Linux containers (this guide is written for **Linux**; Mac/Windows notes are at the end of each item).

### 1.1 A terminal

- **Linux:** any Terminal app.  
- **Mac:** Terminal or iTerm.  
- **Windows:** install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) and use its terminal, or WSL2.

### 1.2 Git (to copy the project)

Download: [https://git-scm.com/downloads](https://git-scm.com/downloads)

**Verify:**

```bash
git --version
```

**Expected output:** a line like `git version 2.43.0` (any 2.x is fine).

### 1.3 Docker Engine + Compose plugin

This project talks to Docker with the command `docker compose` (two words). The old one-word `docker-compose` is not what we use.

| System | What to install |
|--------|-----------------|
| **Linux** | Docker Engine + Compose plugin: [https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/) |
| **Mac** | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) |
| **Windows** | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) |

On Linux, add your user to the `docker` group so you do not need `sudo` every time (then **log out and back in**):

```bash
sudo usermod -aG docker "$USER"
```

**Verify:**

```bash
docker --version
docker compose version
docker info >/dev/null && echo "Docker daemon: OK"
```

**Expected output:**

- `Docker version 24.x` or newer  
- `Docker Compose version v2.x`  
- `Docker daemon: OK`

If you see `permission denied` while talking to `/var/run/docker.sock`, see [Docker permission issues](#docker-says-permission-denied).

### 1.4 Disk space

Plan on several gigabytes. Dev uses Docker volumes. Prod and stage use folders under `/mnt/fast/`.

**Verify you are in the project folder** (path may differ if you cloned elsewhere):

```bash
cd /opt/stacks/quant-hub
ls docker-compose.yml scripts/run_env.sh .env.dev.example
```

**Expected output:** those three names printed with no “No such file” error.

---

## 2. What is an “environment file”? (plain English)

A `.env` file is a **sticky note of secrets and settings** that Docker reads when it starts the stack. It is ordinary text: `NAME=value` on each line.

| File | What it is |
|------|------------|
| `.env.dev.example` | A **template**. Safe to commit. Full of fake passwords. |
| `.env.dev` | **Your** copy. Real (or practice) passwords. Never commit. |
| Same idea for `.env.stage` / `.env.prod` | |

The application does **not** open these files itself. `scripts/run_env.sh` hands them to Docker. Docker puts the values into the running containers. Python then reads `DATABASE_URL` and `LOG_LEVEL` from the process environment.

You will **copy** a template, then **edit** two things at minimum: the database password, and (for prod/stage) email settings if you want digest mail.

---

## 3. Step-by-step: first-time **dev** setup

Do these in order. Each step has an action, a command, what success looks like, and a check.

### Step 3.1 — Copy the practice settings file

**Action:** In the project folder, duplicate the template.

```bash
cd /opt/stacks/quant-hub
cp .env.dev.example .env.dev
```

**Expected output:** no message (Unix copies are silent when they work).

**Verification:**

```bash
test -f .env.dev && echo "env file exists"
```

You should see `env file exists`.

### Step 3.2 — Set a practice password

**Action:** Open `.env.dev` in any editor (VS Code, nano, etc.).

Change **both** places the password appears so they match:

1. `POSTGRES_PASSWORD=dev-only-change-me`  
2. The password inside `DATABASE_URL=postgresql://quant:dev-only-change-me@postgres:5432/quant_hub_dev`

Example after edit:

```text
POSTGRES_PASSWORD=my-practice-password
DATABASE_URL=postgresql://quant:my-practice-password@postgres:5432/quant_hub_dev
```

Leave `LOG_LEVEL=DEBUG` and `APP_ENV=dev` as they are.

You can leave SMTP lines empty in dev. Email will simply not send.

**Verification:** the two passwords are identical, and there are **no spaces** around `=`.

### Step 3.3 — Start the practice stack

**Action:** Build images and start two containers (database + app). The first build can take several minutes.

```bash
cd /opt/stacks/quant-hub
./scripts/run_env.sh dev up --build
```

To run in the background instead (terminal stays free):

```bash
./scripts/run_env.sh dev up --build -d
```

**Expected output (success):** lines about building, then something like:

```text
Container quant-hub-db-dev  Started
Container quant-hub-dev     Started
```

If you did **not** use `-d`, logs will keep printing in that terminal. That is normal. Open a **second** terminal for the next commands.

**Verification:**

```bash
./scripts/run_env.sh dev ps
```

Both `postgres` and `quant-hub` should show `running` (or `healthy` for postgres).

### Step 3.4 — Ask the app if the database is reachable

**Action:** Run the status command **inside** the app container.  
Dev container name is `quant-hub-dev`.

```bash
docker exec quant-hub-dev quant-hub status
```

**Expected output:**

```text
Database: OK
  scan_runs: 0
  ticker_results: 0
  ...
```

Zeros are fine on a brand-new database.

**Verification:** if you see `Database: UNREACHABLE` or `DATABASE_URL is required`, see [troubleshooting](#8-common-troubleshooting).

### Step 3.5 — Open the dashboard

**Action:** In a web browser, go to:

`http://127.0.0.1:5002`

**Expected output:** a Quant Hub page (Command Center / Launchpad / Lynch). An empty briefing is normal until you run a scan.

**Verification:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5002
```

You want `200` (page loaded) or `302` (redirect). `000` means nothing is listening.

### Step 3.6 — (Optional) Run one tiny scan

This downloads prices from the internet (Yahoo). It can take a minute.

```bash
docker exec quant-hub-dev quant-launchpad --tickers NVDA --cache --report json
```

**Expected output:** log lines, then a successful persist message.  
**Verification:** `docker exec quant-hub-dev quant-hub status` should show `scan_runs` at least 1. Refresh the dashboard.

---

## 4. Stage (optional dress rehearsal)

Stage is **prod-shaped** but uses a **different disk** so you cannot overwrite live history.

**Action:** create host folders (one-time, needs sudo):

```bash
sudo mkdir -p /mnt/fast/quant-data-stage/{postgres,data,logs}
sudo chown -R "$USER:$USER" /mnt/fast/quant-data-stage
```

**Copy settings:**

```bash
cd /opt/stacks/quant-hub
cp .env.stage.example .env.stage
```

Edit `.env.stage`: set a **new** `POSTGRES_PASSWORD` and the matching password inside `DATABASE_URL`. Database name must stay `quant_hub_stage`.

**Start:**

```bash
./scripts/run_env.sh stage up --build -d
./scripts/run_env.sh stage ps
docker exec quant-hub-stage quant-hub status
```

Dashboard: `http://127.0.0.1:5003`  
Postgres on the host: `127.0.0.1:5434`

---

## 5. Prod (live homelab)

Use this only when you intend to use `/mnt/fast/quant-data` (the existing live volume).

**Copy settings:**

```bash
cd /opt/stacks/quant-hub
cp .env.prod.example .env.prod
```

Edit `.env.prod`:

1. Set a **strong** `POSTGRES_PASSWORD`.  
2. Put the **same** password in `DATABASE_URL`.  
3. Keep `POSTGRES_DB=quant_hub` if this is the existing live database.  
4. Fill `SMTP_*` and `EMAIL_TO` if you want digest emails.

**Start (background):**

```bash
./scripts/run_env.sh prod up --build -d
./scripts/run_env.sh prod ps
docker exec quant-hub quant-hub status
```

Prod container names stay `quant-hub` and `quant-hub-db` (same as the historic stack).  
Dashboard: `http://127.0.0.1:5002` (loopback only).  
Host Postgres: `127.0.0.1:5433`.

**Universe files in prod:** the container reads `/mnt/fast/quant-data/data/`, not only the git `data/` folder. After you edit `data/universes/*.txt` in git, copy them to the live volume:

```bash
cp /opt/stacks/quant-hub/data/universes.json /mnt/fast/quant-data/data/universes.json
cp /opt/stacks/quant-hub/data/universes/mega_runners.txt /mnt/fast/quant-data/data/universes/mega_runners.txt
docker exec quant-hub quant-universe show mega_runners
```

---

## 6. Everyday commands (cheat sheet)

Replace `dev` with `stage` or `prod` as needed.

| What you want | Command |
|---------------|---------|
| Start (rebuild images) | `./scripts/run_env.sh dev up --build -d` |
| See running containers | `./scripts/run_env.sh dev ps` |
| Follow logs | `./scripts/run_env.sh dev logs -f --tail 80` |
| Stop (keep data) | `./scripts/run_env.sh dev down` |
| Status inside the app | `docker exec quant-hub-dev quant-hub status` |
| Makefile shortcut | `make dev-up` / `make down-dev` |

| Environment | App container | DB container | Dashboard | Host DB port |
|-------------|---------------|--------------|-----------|--------------|
| dev | `quant-hub-dev` | `quant-hub-db-dev` | 5002 | 5433 |
| stage | `quant-hub-stage` | `quant-hub-db-stage` | 5003 | 5434 |
| prod | `quant-hub` | `quant-hub-db` | 5002 (localhost only) | 5433 |

Makefile targets do **not** set `COMPOSE_PROJECT_NAME`. Prefer `./scripts/run_env.sh` so stacks stay isolated.

---

## 7. How configuration is read (no jargon)

1. You run `./scripts/run_env.sh dev up`.  
2. The script passes `--env-file .env.dev` plus two Compose files.  
3. Docker starts Postgres with `POSTGRES_PASSWORD` / `POSTGRES_DB`.  
4. Docker starts the app with `DATABASE_URL` and `LOG_LEVEL`.  
5. On boot, `docker/entrypoint.sh` copies those values so scheduled jobs can see them.  
6. Python `config.database_url()` reads `DATABASE_URL`. `logging_setup.py` reads `LOG_LEVEL`.

You never type the database password into Python. If status says `DATABASE_URL is required`, the container did not receive the variable — recreate the stack after fixing `.env.dev`.

---

## 8. Common troubleshooting

### “Missing .env.dev — copy from .env.dev.example”

You skipped Step 3.1. Run `cp .env.dev.example .env.dev` in `/opt/stacks/quant-hub`.

### “Set POSTGRES_PASSWORD in the env file”

Compose interpolated an empty password. Open `.env.dev` (or `.env.prod`) and set `POSTGRES_PASSWORD=...` with no quotes unless the password itself contains spaces (avoid spaces).

### Port already in use (`bind: address already in use`)

This stack does **not** use Redis/Valkey. Typical clashes:

| Port | Who wants it | What to do |
|------|----------------|------------|
| **5002** | Dev or prod dashboard | Stop the other Quant Hub env, or change `DASHBOARD_PORT` in the `.env` file |
| **5003** | Stage dashboard | Change `DASHBOARD_PORT` in `.env.stage` |
| **5433** | Dev or prod Postgres on the host | Stop the other stack, or change `POSTGRES_PORT` |
| **5434** | Stage Postgres | Change `POSTGRES_PORT` in `.env.stage` |
| **5432** | Some other Postgres on the machine | This project binds **5433/5434** on the host, so a local 5432 Postgres is usually fine |

See what is using a port (Linux):

```bash
ss -ltnp | grep -E '5002|5003|5433|5434'
```

Stop a Quant Hub env you started earlier:

```bash
./scripts/run_env.sh dev down
./scripts/run_env.sh prod down
```

Do **not** run `dev` and `prod` at the same time if both use host port 5002 or 5433.

### Docker says “permission denied”

On Linux:

```bash
groups
```

If `docker` is not listed, run `sudo usermod -aG docker "$USER"`, then log out and back in. Until then you can prefix commands with `sudo` (not ideal).

### `Database: UNREACHABLE`

```bash
./scripts/run_env.sh dev ps
./scripts/run_env.sh dev logs postgres --tail 40
```

Wait until postgres is `healthy`. Confirm `POSTGRES_PASSWORD` matches the password inside `DATABASE_URL`. Recreate after edits:

```bash
./scripts/run_env.sh dev up -d --force-recreate
```

### Dashboard is empty

That means **no scan is stored yet**, not that setup failed. Run Step 3.6 or wait for scheduled jobs (prod/stage only; they use `docker/crontab`).

### `Unknown universe`

In **prod**, you edited git `data/universes/` but did not copy files to `/mnt/fast/quant-data/data/`. See [Prod universe copy](#5-prod-live-homelab).  
In **dev**, universe files are bind-mounted from the repo; a typo in `quant-universe list` is more likely.

### Code change has no effect

- **Dev:** `./src` is mounted; Streamlit often picks up dashboard edits. CLI scans use the mounted code on the **next** command.  
- **Stage/prod:** no source mount. Rebuild: `./scripts/run_env.sh prod up --build -d`.

### Old instructions: `docker compose up -d` or `cp .env.example .env`

Those are **obsolete**. They used a single `.env` and a compose file that always pointed at `/mnt/fast/quant-data`. Use this guide and `./scripts/run_env.sh` instead. `.env.example` is a pointer stub only — copy `.env.dev.example`, `.env.stage.example`, or `.env.prod.example`.

### Email never arrives

Empty `SMTP_HOST` is expected in dev. For prod, set `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_TO`, then:

```bash
./scripts/run_env.sh prod up -d --force-recreate
```

---

## 9. Stop and clean up

Stop containers, **keep** data:

```bash
./scripts/run_env.sh dev down
```

Dev data lives in Docker volumes (`quant-hub-pg-dev`, etc.). Removing volumes **deletes** the practice database:

```bash
./scripts/run_env.sh dev down -v
```

Never run `down -v` on **prod** unless you intend to destroy `/mnt/fast/quant-data/postgres` usage for that stack (the bind mount itself remains on disk).

---

## 10. What to read next

| Goal | Doc |
|------|-----|
| What the dashboard pages mean | [User Manual](USER_MANUAL.md) |
| How Launchpad scores work | [Launchpad Scanner](LAUNCHPAD_SCANNER.md) |
| Day-2 operations, backups | [Runbook](RUNBOOK.md) |
| ML after the stack is up | [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) |
| Learn the ML pipeline | [ML Operations Course](ML_OPERATIONS.md) |
| Database tables | [Junior Developer Database Guide](JUNIOR_DEV_DATABASE_GUIDE.md) |

---

## Audit notes (what this guide replaced)

The following **setup** recipes were outdated after the multi-environment Compose split and must not be followed:

- `cp .env.example .env` then `docker compose up -d --build`
- Bare `docker compose up` / `docker compose ps` without `run_env.sh` (base compose has no volumes)
- Treat host port 5002 + `/mnt/fast/quant-data` as the only way to run (that is **prod** only)

Schedule tables in older manuals sometimes still mention weekday `sp500_index` at 5:10 PM. **`docker/crontab` is the source of truth** (weekday growth universes, digest at 5:40 PM ET).
