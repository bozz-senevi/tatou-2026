# CI/CD setup

CI and CD are two separate workflows:

- **CI** — [workflows/ci.yml](workflows/ci.yml), trigger `pull_request` → `main`.
- **CD** — [workflows/cd.yml](workflows/cd.yml), trigger `push` → `main` (i.e. a merge).

| Workflow | Stage         | Runs on           | When                        | Does                                      |
|----------|---------------|-------------------|-----------------------------|-------------------------------------------|
| CI       | `test`        | GitHub-hosted     | PR opened/updated vs `main` | `pip install -e .[dev]` then `pytest`     |
| CI       | `security`    | GitHub-hosted     | PR opened/updated vs `main` | bandit + pip-audit (advisory, non-blocking) |
| CI       | `integration` | GitHub-hosted     | PR opened/updated vs `main` | real server + MariaDB service: healthz → create-user → login → list-documents |
| CI       | `build`       | GitHub-hosted     | PR opened/updated vs `main` | `docker build ./server` (validates image) |
| CD       | `build`       | GitHub-hosted     | merge to `main`             | `docker build ./server` (gate before deploy) |
| CD       | `deploy`      | self-hosted on VM | merge to `main`             | pull main, `docker compose up -d --build`, health check |

**No duplicate runs:** a plain push to a feature branch runs nothing; opening/updating
a PR runs CI only; merging the PR runs CD only. CI does not run on merge, and CD does
not run on PRs.

Because CD assumes CI already validated the change, protect `main` so only
CI-passing PRs can merge — see "Require CI before merge" below.

The `integration` stage spins up a throwaway `mariadb:11.4` service, loads
[`db/tatou.sql`](../db/tatou.sql), starts the real app under gunicorn, and
exercises the live auth path against the database — catching DB/schema breakage
that the unit tests (which run without a database) cannot see.

## One-time setup on the VM

### 1. Install the self-hosted runner

On your VM, from your GitHub repo: **Settings → Actions → Runners → New self-hosted runner**, choose Linux, and follow the shown commands. Then give it the label the workflow expects:

```bash
# during ./config.sh you are asked for labels — add: tatou-vm
# or re-run config with:
./config.sh --url https://github.com/<you>/tatou-2026 --token <TOKEN> --labels tatou-vm
```

Run it as a service so it survives reboots:

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

The runner connects **outbound** to GitHub, so it works from the isolated network with no inbound access.

### 2. Let the runner use Docker

The runner's user must run `docker compose` without sudo:

```bash
sudo usermod -aG docker $USER   # then log the runner's session out/in (or restart the svc)
```

### 3. Point the deploy at your live checkout

The deploy stage runs in the directory that holds your **gitignored** `.env`, `server/keys/`, and the docker volumes — not a fresh clone. Set it as a repo **variable** (not a secret):

**Settings → Secrets and variables → Actions → Variables → New repository variable**

```
Name:  DEPLOY_DIR
Value: /home/softsec/phase1/tatou-2026
```

### 4. Require CI before merge (branch protection)

CD trusts that CI already ran, so make CI a merge gate. **Settings → Branches →
Add branch ruleset (or rule) for `main`**, and enable **Require status checks to
pass before merging**; select the CI jobs (`Unit tests`, `Integration smoke test`,
`Build server image`). Optionally **Require a pull request before merging** so
nothing lands on `main` without a PR. With this, a PR whose CI failed cannot be
merged, so CD never deploys an unvalidated change.

(`Security scan` is advisory — leave it out of the required checks, or it would
block merges on findings.)

### 5. (Optional) require a manual approval before deploy

The deploy job uses the `production` environment. Under **Settings → Environments → production** you can add yourself as a **required reviewer** so each deploy waits for a click.

## Important notes

- **`git reset --hard origin/main`** in the deploy makes the VM checkout match `main` exactly. Anything uncommitted on the VM (outside gitignored files like `.env`/`keys/`) is discarded. Keep server config in `.env`, never as live edits in tracked files.
- **`.env`, `server/keys/`, and volumes are preserved** across deploys — they're gitignored and `docker compose` reuses the named volumes (`db-data`, `user-files`), so the database and uploaded PDFs (including flag 3) survive a redeploy.
- **Secrets stay on the VM.** The pipeline never needs your `SECRET_KEY`, DB password, or RMAP passphrase in GitHub — they live in the VM's `.env`.
- If `test` relies on the RMAP git dependency, the GitHub-hosted runner needs outbound git (it has it by default).
