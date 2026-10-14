# Collection of Changes: Observation Points & Recovery (Specialization D)

**Course deliverable covered:** "A collection of changes made on the project to: (i) add
observation points to detect attacks, (ii) recover from attacks." The reasoning behind
which observation points matter is in `threat-model.md` Section 9; the underlying
vulnerabilities being recovered from are in `threat-model.md` Section 6. This document is
the evidence that both were actually implemented, with verification.

## Part I: Observation points

Four observation points, implemented in `server/src/server.py` and `db/tatou.sql`.

### 1. Persistent logging

A `RotatingFileHandler` writes to `STORAGE_DIR/logs/app.log`, inside the `user-files`
Docker volume, so it survives a container rebuild. 6.5's logs were lost entirely to a
routine `docker compose up --build`; this fixes that.

**Verification:** log lines from before a `docker compose restart` are still present
after it.

### 2. Ownership-check failure visibility

An `after_request` hook logs every request's method, path, status, user, and IP, at
`WARNING` for `401`/`403`/`404`/`429`. On the ownership-checked routes (`get-document`,
`list-versions`, `create-watermark`, `read-watermark`, `delete-document`), a 404 can mean
"someone tried to touch a document they don't own," not just a typo in the URL.

**Verification:** a request to `get-document/999999` without a valid token produced a
`WARNING` line with status, user, and IP recorded.

### 3. RMAP handshake logging

Both `rmap-initiate` and `rmap-get-link` log identity and source IP, on success and on
failure (unknown identity, malformed payload, RMAP/DB errors).

**Verification:** a full live handshake (`scripts/handshake_test.py`) produced matching
`INFO` lines for both endpoints with the correct identity and IP; the unknown-identity and
malformed-payload negative tests produced matching `WARNING` lines.

### 4. `Versions` creation timestamp

`created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6)` added to the `Versions` table
(`db/tatou.sql`, plus an idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migration
for already-initialized databases). Fixes the gap found while investigating 6.5, where the
database evidence could only bound the exploitation to "before the container was recreated."

**Verification:** two new `Versions` rows created via live RMAP handshakes both carry a
real `created_at` timestamp. Rows that existed before the migration were backfilled with
the migration's run time, not their real original creation time, so pre-migration rows
should not be read as historical evidence.

**Status:** All four implemented and verified locally. Not yet deployed to the course VM.

## Part II: Recovery actions

What was done after each confirmed compromise, not the vulnerability fix itself (that's
Section 6 of the threat model) but the response to the compromise.

### 1. flag_3 rotation

**Trigger:** flag_3 (document 24, owned by `Mr_Important`) was captured by 
other groups through the `create-watermark` ownership gap (threat-model.md 6.1),
exploited before the fix was deployed. Confirmed via `Versions` records 34, 53
(sweep by `Tiwwavignsw@gmail.com` / `Yjgqfozcyvn@gmail.com`) and 85 (Group 16).

**Action taken:**
- Root cause patched: `AND ownerid = :uid` added to `create-watermark`'s document lookup.

- flag_3 rotated. New value supplied by the course instructor.
  The flag is stored as literal text in the PDF's content stream.  The original was backed up before
  editing.

**Verification:** a fresh test user calling `create-watermark/24` after the fix returns
`{"error": "document not found"}`, confirming the exploited path is closed. The rotated
value was confirmed readable from the PDF after re-encoding.

**Status:** Closed.

### 2. Ownership-check gap across three routes

**Trigger:** `read-watermark`, `create-watermark`, and `delete-document` queried
`Documents` by id only, with no `ownerid` check, letting any authenticated user act on a
document they didn't own (threat-model.md 6.1, 6.2). `delete-document` additionally had
no `@require_auth` decorator at all and concatenated the id directly into SQL.

**Action taken:**
- `read-watermark`: ownership check added.
- `create-watermark`: ownership check added.
- `delete-document`: `@require_auth` added (was missing entirely), the concatenated query
  replaced with a parameterized `text(...)` query bound to `:id AND ownerid = :uid`.

**Verification:** each fix was tested live, before and after, with a second test account
attempting to read/watermark/delete a document it didn't own: before the fix the action
succeeded (confirming the gap), after the fix it returned `{"error": "document not
found"}` or `401`, matching the ownership-scoped behavior of the already-correct routes
(`get-document`, `list-versions`).

**Status:** Fixed, tested, and deployed.
