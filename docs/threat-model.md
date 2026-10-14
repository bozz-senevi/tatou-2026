# Threat Model: Tatou (Group 30)

**Course:** SOFTSEC VT2026
**Specialization:** D, Operational Security (Threat Modeling, Logging & Monitoring)
**Author:** Bhanu
**Scope:** `server/src/server.py`, the MariaDB backend, the Docker Compose deployment, and the RMAP endpoints introduced in Phase I.

## Abstract

This threat model is built from evidence gathered during development and operation. Every
finding is backed by a real test or a real incident.
## 1. System Overview

Tatou's backend is a Flask app backed by MariaDB. Uploaded PDFs are stored on disk, one folder
per user. Three trust boundaries matter:

1. **Unauthenticated public routes.** `healthz`, `create-user`, `login`,
   `get-watermarking-methods`, `get-version/<link>`, and the two RMAP endpoints. By design:
   recipients don't need an account, and RMAP handles its own authentication.
2. **Authenticated routes, scoped to the caller.** Everything else should only touch the
   requesting user's own resources.
3. **Mutual trust between servers via RMAP.** Established purely by possession of the
   corresponding PGP private key, with no secondary check.

## 2. Assets

| Asset | Why it matters |
|---|---|
| User credentials (`Users.hpassword`) | Compromise = impersonate any account |
| Uploaded document content | Confidentiality is the platform's core guarantee |
| Watermark secrets (`Versions.secret`) | Leak-attribution depends on these staying unrecoverable without the key |
| RMAP key material (`server_priv.asc`, `RMAP_WATERMARK_KEY`, passphrases) | Compromise = impersonate our server, or forge/verify attribution |
| Course flags | Direct grading consequence if disclosed |
| Service availability | Needed throughout Phase II for RMAP exchanges with other groups |

## 3. Threat Actors

- **Other course groups.** The primary, intended actor for this course.
- **Internal process failure.** A teammate briefly committed the real flag value to git, then
  reverted it. It remains recoverable from history. A real, demonstrated exposure path.
- **Opportunistic scanning.** Lower priority, on the assumption the course network is isolated.
  Section 6.6 notes that assumption shouldn't be treated as guaranteed.

## 4. Attack Surface

| Route | Auth | Note |
|---|---|---|
| `GET /healthz` | None | Liveness only |
| `create-user`, `login` | None (by design) | |
| `get-watermarking-methods` | None | Read-only |
| `get-version/<link>` | None (by design) | Public distribution endpoint |
| `rmap-initiate`, `rmap-get-link` | PGP identity | Inter-group handshake |
| `upload-document` | Required | See 6.3 |
| `list-documents`, `get-document/<id>` | Required | Correctly owner-scoped |
| `delete-document/<id>` | **Missing in implementation** | See 6.2 |
| `create-watermark/<id>`, `read-watermark/<id>` | Required | See 6.1 |
| `list-versions/<id>`, `list-all-versions` | Required | Correctly owner-scoped |
| `load-plugin` | N/A | Disabled; see 6.4 |
| phpMyAdmin, MariaDB ports | DB credentials | Should not be host-external; see 6.6 |

## 5. Methodology

STRIDE was applied after the fact, only as a check for missed categories. It flagged
Repudiation as under-addressed in our logging. Addressed in Section 9. Findings below are in
discovery order, since the chronology matters for 6.1 and 6.5.

## 6. Findings

### 6.1 Missing ownership check in three routes

`read-watermark`, `create-watermark`, and `delete-document` all queried `Documents` by id only,
no `ownerid` check:

```python
# lookup the document; enforce ownership
row = conn.execute(
    text("SELECT id, name, path FROM Documents WHERE id = :id LIMIT 1"),
    {"id": doc_id},
).first()
```

Any authenticated user could act on a document they didn't own. All three confirmed fixed; no
fourth instance found elsewhere in the file.

`create-watermark` is the most severe: `get-version/<link>` is public, so the missing check let
anyone generate a public download link to a document's full content. Evidence and exploitation
timeline in 6.5.

### 6.2 `delete-document`: no auth, plus SQL injection

```python
query = "SELECT * FROM Documents WHERE id = " + doc_id
row = conn.execute(text(query)).first()
```

Three defects: `@require_auth` missing, same ownership gap as 6.1, and the id concatenated
directly into SQL instead of bound.

Confirmed by submitting
`0 UNION SELECT id, login, hpassword, email, NULL, NULL, NULL FROM Users LIMIT 1-- -` as the id;
executed without a SQL error, proving the injection point accepts a valid `UNION`.

### 6.3 `upload-document`: no content check, unsanitized filename

Uploaded content wasn't validated as a real PDF. The client filename was used unsanitized to
build the storage path, so a name like `x/../../../../tmp/pwned.pdf` could write outside the
intended directory. Confirmed with that exact payload; `secure_filename()` neutralizes it.

### 6.4 `load-plugin`: removed.
Deserialized user-supplied files with `pickle`/`dill`. Unpickling untrusted data executes
arbitrary code via `__reduce__` during deserialization itself, before any validation in the
function runs. The deserialization call itself is the unsafe operation. (A separate
path-containment bug existed too: `Path.__truediv__` drops the left operand when the right is
absolute.)

### 6.5 flag_3: confirmed

flag_3 (document 24, owned by `Mr_Important`) was captured. Root cause: the `create-watermark`
defect in 6.1.

`Versions` records against document 24:

| version_id | intended_for | secret | method |
|---|---|---|---|
| 34 | `Tiwwavignsw@gmail.com_toy-eof_neo` | `..._red_or_blue` | toy-eof |
| 53 | `Yjgqfozcyvn@gmail.com_toy-eof_neo` | `..._red_or_blue` | toy-eof |
| 68 | `group30-audit` | `audit-secret-2026` | stealth-invisible |
| 85 | `g16-audit` | `g16-audit-secret` | toy-eof |

Record 68 is our own (self-labeled, our own `stealth-invisible` method). The other three are
exploit evidence: `Tiwwavignsw@gmail.com` and `Yjgqfozcyvn@gmail.com` (records 34, 53) ran a
scripted sweep hitting documents 1, 2, 3, 8, 18, 19, 24, 25, and 27, not just this one. Record 85
is Group 16, self-labeled `g16-audit`.



**Fix:** `AND ownerid = :uid`, matching the existing `get-document` pattern. 

Verified: a fresh test user calling `create-watermark/24` now gets
`{"error": "document not found"}`.

**flag_3 rotated:** New value from the course instructor. Stored as
literal text in the PDF's content stream.


**Observability gap:** server logs for the exploitation window were lost when the container was
recreated. `Versions` has no creation timestamp either, so the database evidence
only bounds the event to "before the container was recreated." Both addressed in Section 9.

### 6.6 Host configuration: file permissions and exposed ports

`.env` and `server/keys/` were world-readable (`644`) instead of owner-only. phpMyAdmin and
MariaDB were bound to all interfaces instead of loopback. Both fixed.

### 6.7 No rate limiting on `login` and `create-user`

Neither `login` nor `create-user` capped request attempts.

**Fix:** per-route, per-IP sliding-window limit, 5 requests/60s. Verified: 6th rapid login
attempt returns `429`; a legitimate login succeeds normally once the window passes. In-memory,
single-process, same constraint as RMAP's identity cache (Section 7).

**Status:** Fixed, tested, and deployed.

## 7. RMAP Trust-Model Risks

Client identities are cached for the server process's lifetime. A newly published group key
does nothing until restart. A plausible way to lose time during an active capture window.

RMAP's security assumes every group's published key is authentic. Neither we nor anyone else
can detect a stale or substituted key circulating under an identity. This is a limitation of the
protocol itself.

## 8. Explicitly Out of Scope

Other groups' infrastructure is out of scope, by the course's own rules. Physical and
hypervisor-level compromise is out of scope too, since no application-level change addresses it.

## 9. What This Drives: Monitoring

Four prioritized observation points:

- `401`/`403`/`404` on ownership-checked routes. Would have surfaced 6.1 and 6.2 as they
  happened.
- Every RMAP handshake, logged by identity and source address. Covers the Repudiation gap and
  gives visibility into cross-group activity as it happens, not after the fact.
- A creation timestamp on every `Versions` record. Fixes the gap found while investigating 6.5.
- Logs shipped somewhere that survives a container restart, not just stdout inside the
  container. 6.5's logs were lost entirely to a routine `docker compose up --build`; the same
  rebuild during any future incident would do the same otherwise.

Implementation, verification, and the recovery actions taken after the compromises above
(flag_3 rotation, the 6.1/6.2 ownership fixes) are collected separately in
`docs/observation-points-and-recovery.md`.

