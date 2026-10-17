# Tatou

A web platform for PDF watermarking. This project is intended for pedagogical use, and contains security vulnerabilities. Do not deploy on an open network.

## Overview

Tatou lets a document owner embed a traceable secret into a PDF so that any leaked copy can be attributed back to the recipient it was given to:

1. **Upload** a confidential PDF.
2. **Watermark** it, producing a uniquely identifiable version for a specific recipient using one of several methods.
3. **Share** a secret link to that watermarked version.
4. **Attribute a leak** by reading the watermark out of a recovered copy.

Users authenticate with an email/password, receive a bearer token, and operate only on their own documents and versions. A separate PGP-based handshake (RMAP) lets other parties authenticate and retrieve an individually watermarked copy of a designated document without an account.

### Watermarking methods

Each method embeds an HMAC-authenticated secret and is addressed by a stable `name`:

| Name | Technique |
|------|-----------|
| `toy-eof` | Appends an authenticated record after the PDF's final `%%EOF` marker. |
| `stealth-invisible` | Invisible text (render mode 3) on every page **and** the `Keywords` metadata field. |
| `iman-wm` | Three independent locations: an extra catalog object, an `Info`-dictionary entry, and invisible page text. |
| `sussann-watermark` | Stores the secret and a key hash in the document metadata. |

Query the live list at runtime via `GET /api/get-watermarking-methods`.

## Architecture

| Component | Tech | Notes |
|-----------|------|-------|
| Backend | Flask + Gunicorn (Python) | REST API in `server/src`, served on port 5000. |
| Database | MariaDB | `Users`, `Documents`, `Versions` tables (`db/tatou.sql`). |
| Storage | Docker volume | Uploaded and watermarked PDFs under `/app/storage`. |
| Webapp | HTML/JS | Static client served from `server/src/static`. |

Containers are orchestrated with `docker-compose.yml` (server, db, phpMyAdmin). The database and phpMyAdmin are bound to loopback; only the API (port 5000) is exposed to the network.

## Instructions

The following instructions are meant for a bash terminal on a Linux machine. If you are using something else, you will need to adapt them.

To clone the repo, you can simply run:

```bash
git clone https://github.com/nharrand/tatou-2026.git
```

Note that you should probably fork the repo and clone your own repo.

### Run python unit tests

```bash
cd tatou/server

# Create a python virtual environement
python3 -m venv .venv

# Activate your virtual environement
. .venv/bin/activate

# Install the necessary dependencies
python -m pip install -e ".[dev]"

# Run the unit tests
python -m pytest
```

### Measure test coverage

Some tests (the API findings tests in `test_api_findings.py`) need the running
stack, so start the stack first, then run pytest with coverage. The HTML report
is written to `artifacts/common/coverage/` (open `index.html`).

```bash
docker compose up -d --build
cd server
pip install pytest pytest-cov
TATOU_BASE=http://localhost:5000 PYTHONPATH=src python -m pytest test/ --cov=src --cov-report=html:../artifacts/common/coverage --cov-report=term-missing
```

A specification-to-test mapping is in `artifacts/common/specification_test_mapping.html`.

### Deploy

From the root of the directory:

```bash
# Create a file to set environement variables like passwords.
cp sample.env .env

# Edit .env and pick the passwords you want

# Rebuild the docker image and deploy the containers
docker compose up --build -d

# Monitor logs in realtime 
docker compose logs -f

# Test if the API is up
http -v :5000/healthz

# Open your browser at 127.0.0.1:5000 to check if the website is up.
```

## Configuration

Environment variables (set in `.env`, consumed via `docker-compose.yml`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SECRET_KEY` | `dev-secret-change-me` | Signing key for auth tokens. **Set a strong random value** — the default makes tokens forgeable. |
| `TOKEN_TTL_SECONDS` | `86400` | Bearer-token lifetime. |
| `STORAGE_DIR` | `/app/storage` | Where PDFs are stored. |
| `LOG_DIR` | `/app/logs` | Rotating `app.log` with the request audit trail. |
| `RATE_LIMIT_MAX` | `100` | Max requests per window per IP on auth routes (`0` disables). |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window. |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `db` / `3306` / `tatou` / … | Database connection. |
| `RMAP_KEYS_DIR` | `/app/keys` | Server PGP keypair and client public keys (`clients/`). |
| `RMAP_DOCUMENT_ID` | — | Document served by RMAP, watermarked per requester. |
| `RMAP_WATERMARK_METHOD` | `toy-eof` | Method used for RMAP-delivered copies. |
| `RMAP_WATERMARK_KEY` | `dev-rmap-key-change-me` | Key for the RMAP watermark. |
| `RMAP_SERVER_KEY_PASSPHRASE` | — | Passphrase for the server's PGP private key. |

## API

Base URL: `http://<host>:5000`. Authenticated routes require an `Authorization: Bearer <token>` header obtained from `login`. All request/response bodies are JSON unless a file is returned.

### Public endpoints (no authentication)

| Method | Path | Body / Params | Returns |
|--------|------|---------------|---------|
| `GET` | `/healthz` | — | `{message, db_connected}` |
| `POST` | `/api/create-user` | `{login, email, password}` | `{id, login, email}` |
| `POST` | `/api/login` | `{email, password}` | `{token, token_type: "bearer", expires_in}` |
| `GET` | `/api/get-watermarking-methods` | — | `{methods: [{name, description}], count}` |
| `GET` | `/api/get-version/<link>` | — | Watermarked PDF (by secret link) |
| `GET` | `/` , `/<path>` | — | Static webapp |

`create-user` and `login` are rate-limited (see `RATE_LIMIT_MAX`).

### Authenticated endpoints (Bearer token; scoped to the caller's own data)

| Method | Path | Body / Params | Returns |
|--------|------|---------------|---------|
| `POST` | `/api/upload-document` | multipart: `file` (PDF), `name` | `{id, name, creation, sha256, size}` |
| `GET` | `/api/list-documents` | — | `{documents: [{id, name, creation, sha256, size}]}` |
| `GET` | `/api/get-document/<id>` | — | PDF file (owner only) |
| `DELETE` | `/api/delete-document/<id>` | — | `{deleted, id, file_deleted, file_missing}` |
| `GET` | `/api/list-versions/<id>` | — | `{versions: [{id, documentid, link, intended_for, secret, method}]}` |
| `GET` | `/api/list-all-versions` | — | `{versions: [...]}` across the user's documents |
| `POST` | `/api/create-watermark/<id>` | `{method, intended_for, secret, key, position?}` | `{id, documentid, link, intended_for, method, position, filename, size}` |
| `POST` | `/api/read-watermark/<id>` | `{method, key, position?}` | `{documentid, secret, method, position}` |

The document id for `create-watermark`, `read-watermark`, and `delete-document` may also be passed as `?id=`/`?documentid=` or in the JSON body.

### RMAP endpoints (public; PGP mutual authentication)

Four-message handshake (Roger Michael Authentication Protocol). Each message is `{"payload": "<base64 of a PGP-armored body>"}`. See the [RMAP library](https://github.com/nharrand/RMAP).

| Method | Path | Decrypted request | Decrypted response |
|--------|------|-------------------|--------------------|
| `POST` | `/api/rmap-initiate` | `{identity, nonceClient}` | `{nonceClient, nonceServer}` |
| `POST` | `/api/rmap-get-link` | `{nonceServer}` | `{result: "<32-hex link>"}` |

On success, `rmap-get-link` creates a watermarked version of `RMAP_DOCUMENT_ID` for the requesting identity and records it; the returned link is retrievable via `GET /api/get-version/<link>`.
