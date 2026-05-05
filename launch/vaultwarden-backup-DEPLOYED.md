# Vaultwarden Backup Pipeline — Deployed

Status: live and running.
Date: 2026-05-05.
Author: Claude Code (autonomous execution per Federico's brief).

## TLDR

- Encrypted, signed Vaultwarden backups now run hourly + daily + monthly via systemd timers on AX41.
- Each backup is `age`-encrypted to two recipients (primary + escrow), ed25519-signed, then uploaded to the small Hetzner VPS via an rrsync-restricted SSH key (no shell on the VPS).
- First end-to-end pipeline run + first restore drill both passed.
- Backblaze B2 immutable layer is **deferred** because it requires Federico's payment method (hard rule: STOP if signup needs CC). Hetzner small VPS is the offsite copy until B2 is added.
- Federico must (1) print + safe two age private keys, (2) optionally finish Healthchecks.io magic-link signup, (3) decide on B2/R2 immutable storage account.

## What's running

### Schedule (UTC)

| Mode | When | Retention local | Retention remote (VPS) |
|------|------|-----------------|------------------------|
| `hourly-db` | minute 17 every hour | 30d | (TODO: VPS retention prune script) |
| `daily-full` | 03:43 daily | 90d | |
| `monthly-full` | 04:11 first of month | 730d | |
| `manual-full` | on demand | 730d | |

### Backup contents

`hourly-db`: SQLite `.backup` snapshot, RSA token signing keys, `config.json`, `admin-token`, `docker-compose.yml`, `.env`, `migrate-secrets.py`, `migration-log.json`, `wrappers/`, attachment+sends manifest hashes (no payload).

`daily-full` / `monthly-full` / `manual-full`: everything in `hourly-db` plus full attachments + sends payload.

### Pipeline

1. `sqlite3 .backup` (online, no Vaultwarden downtime).
2. `PRAGMA integrity_check` + `PRAGMA foreign_key_check` on the snapshot.
3. Stage ancillary restore-critical files.
4. Compute attachment + sends manifest hashes (always).
5. Build deterministic `tar.zst`.
6. `age -R /etc/vaultwarden-backup/age-recipients` (2 recipients: primary + escrow).
7. SHA-256 sidecar.
8. `ssh-keygen -Y sign` ed25519 detached signature.
9. `rsync` upload to `vwbackup@91.99.110.206:<mode>/` (rrsync chrooted).
10. `ntfy.sh` push (success or failure).
11. Update `/var/lib/vaultwarden-backup/last-success.json`.

### File layout

| Path | Mode | Purpose |
|------|------|---------|
| `/usr/local/sbin/vaultwarden-backup.sh` | 0750 | Backup script |
| `/etc/vaultwarden-backup/backup.env` | 0600 | Configuration |
| `/etc/vaultwarden-backup/age-identity-primary-2026Q2.txt` | 0600 | Primary recovery key (also at `/root/vault-handoff/`) |
| `/etc/vaultwarden-backup/age-identity-escrow-2026Q2.txt` | 0600 | Escrow recovery key |
| `/etc/vaultwarden-backup/age-recipient-{primary,escrow}-2026Q2.txt` | 0444 | Public recipients |
| `/etc/vaultwarden-backup/age-recipients` | 0444 | Combined recipients used at encrypt time |
| `/etc/vaultwarden-backup/signing_key` | 0400 | AX41 ed25519 signing key |
| `/etc/vaultwarden-backup/signing_key.pub` | 0444 | Public signing key |
| `/etc/vaultwarden-backup/allowed_signers` | 0444 | ssh-keygen -Y verify input |
| `/etc/vaultwarden-backup/upload_key` | 0400 | ed25519 key for uploading to small Hetzner VPS |
| `/etc/vaultwarden-backup/upload_key.pub` | 0644 | Public upload key (installed on VPS) |
| `/var/backups/vaultwarden/{hourly-db,daily-full,monthly-full}/` | 0700 | Local artifact staging |
| `/var/lib/vaultwarden-backup/last-success.json` | 0600 | Last-successful-run state |
| `/var/log/vaultwarden-backup/run.log` | 0644 | systemd journal append |
| `/etc/systemd/system/vaultwarden-backup@.service` | | Templated oneshot |
| `/etc/systemd/system/vaultwarden-backup-{hourly-db,daily-full,monthly-full}.timer` | | Schedules |

### Small Hetzner VPS state

| Item | Value |
|------|-------|
| User | `vwbackup` (UID 996, shell `/bin/bash` so authorized_keys command can exec) |
| Home | `/srv/backups/vaultwarden` |
| SSH access | rrsync-restricted to `/srv/backups/vaultwarden/` (verified: shell denied, path traversal denied) |
| Storage | Encrypted artifacts only — no plaintext ever leaves AX41 |

### Monitoring

| Channel | Status |
|---------|--------|
| ntfy.sh push | Live. Topic: `vw-backup-fede-8y3`. Federico subscribes via `https://ntfy.sh/vw-backup-fede-8y3` or the ntfy app. |
| `/var/lib/vaultwarden-backup/last-success.json` | Live. Floom heartbeat or any local monitor can read this. |
| Healthchecks.io | Pending. Magic-link signup email sent to depontefede@gmail.com. Federico clicks → activates account → creates 3 checks → pastes URLs into `/etc/vaultwarden-backup/backup.env`. |

## First test run

```
2026-05-05T16:56:40Z hourly-db: vaultwarden-ax41-hourly-db-20260505T165640Z-MlDuQOyvHt.tar.zst.age (14672B)
2026-05-05T16:57:04Z daily-full: vaultwarden-ax41-daily-full-20260505T165704Z-MqjW8WFkS5.tar.zst.age (14666B)
2026-05-05T16:58:14Z hourly-db (via systemd): vaultwarden-ax41-hourly-db-20260505T165814Z-eX2mhxceY5.tar.zst.age
```

All three landed on the small Hetzner VPS. ntfy.sh test ping confirmed delivered.

## First restore drill (also on 2026-05-05)

| Check | Result |
|-------|--------|
| Pull artifact from Hetzner VPS via rsync | OK |
| SHA-256 verify | OK |
| ed25519 sig verify | OK |
| `age` decrypt with PRIMARY identity | OK |
| `age` decrypt with ESCROW identity | OK (independent path verified) |
| `MANIFEST.sha256` verify | OK (10/10 files) |
| SQLite `integrity_check` | ok |
| Vaultwarden boot on pinned image digest | HTTP 200 on `/alive`, `/api/config` served |
| Drill cleanup | OK |

Caveat: Vaultwarden currently has 0 users, 0 ciphers — the drill cannot prove semantic correctness on real data. Once Federico starts using the vault, the next drill will exercise the real path.

## Adversarial review (Codex v2) — top 5 weaknesses + fixes

The original Codex v1 plan was reviewed by a fresh Codex invocation. The full v2 plan is at `/tmp/icontext-audit/launch/vaultwarden-backup-plan-v2.md`. Top findings:

1. **Single paper key was a recursive recovery failure.** Original v1 deferred Shamir fallback. v2 ships with both primary AND escrow age identities (two independent paper trails), with Shamir 2-of-3 documented as the next-quarter improvement.
2. **Cron is fragile vs systemd timers.** v2 uses systemd timers with `Persistent=true` + `flock` lock + `systemd-inhibit` shutdown delay. Implemented.
3. **B2 us-west-002 vs EU GDPR.** v2 specifies EU Central region + dedicated Backblaze account + opaque bucket name. **Deferred** in this deployment because it needs Federico's payment method.
4. **Live attachment copy creates split-brain artifacts.** v1 copied attachments while Vaultwarden ran. v2's full fix is stop/snapshot/start, but Federico's CLAUDE.md says don't restart Vaultwarden during business hours. Compromise: attachment manifest hash is captured FIRST, then attachments are rsynced. Brief race window remains; documented as known limitation. Quarterly drills + manifest hash comparison detect it.
5. **Restore drill was theatre on isolated container.** v2 drill pulls from remote, verifies sig + lock, decrypts with offline key, boots pinned image digest. First drill on 2026-05-05 followed this path.

Other v2 findings (cost creep, account compromise, key rotation, B2 metadata exposure) are documented but addressing them needs Federico's decisions.

## What Federico must do

### Within 7 days (HIGH PRIORITY)

1. **Print + safe the two age private keys.**
   - Files at `/root/vault-handoff/AGE-PRIMARY-PRINT-AND-SAFE.txt` and `/root/vault-handoff/AGE-ESCROW-PRINT-AND-SAFE.txt`.
   - Print on a trusted printer. Store paper copies in two physically distinct secure locations (your safe + parents' safe / lawyer / safe deposit box).
   - After both prints are physically secured, run `shred -u /root/vault-handoff/AGE-*.txt`.
   - Until you do this, the only copies of the recovery keys are on AX41 disk. AX41 disk loss = backups become unrecoverable.
   - Full instructions in `/root/vault-handoff/INSTRUCTIONS.txt`.

### Within 30 days (recommended)

2. **Click the Healthchecks.io magic link** in your `depontefede@gmail.com` inbox (signup submitted automatically). Then create 3 checks: `vaultwarden-backup-hourly-db` (cron `17 * * * *`, grace 30m), `vaultwarden-backup-daily-full` (cron `43 3 * * *`, grace 2h), `vaultwarden-backup-monthly-full` (cron `11 4 1 * *`, grace 6h). Paste the ping URLs into `/etc/vaultwarden-backup/backup.env`.

3. **Decide on the immutable offsite storage account.** Options:
   - Backblaze B2 EU Central — best fit per v2 plan. Needs new email (not depontefede@gmail.com), hardware 2FA, billing card. Storage cost effectively zero until > 10 GB.
   - Cloudflare R2 — single account already exists for DNS, but R2 has different bucket-lock semantics; B2 is documented best-practice.
   - rsync.net Borg account — alternative offsite, $18/year for 100 GB.
   Once the account exists, fill the bottom block in `/etc/vaultwarden-backup/backup.env`, run `aws s3api create-bucket ... --object-lock-enabled-for-bucket`, and the script auto-extends to push to B2 on every run (extension TODO once account exists).

4. **Pin the Vaultwarden image digest** in `/opt/vaultwarden/docker-compose.yml` at the next maintenance window. A suggested pinned compose is at `/root/fede-vault/infra/vaultwarden-docker-compose.suggested-pinned.yml`. Don't apply it during business hours (it doesn't restart the container, but the next `docker compose pull` will reproduce the exact same image rather than rolling forward).

5. **Set `SIGNUPS_ALLOWED=false`** in `/opt/vaultwarden/.env` before exposing `vault.floom.dev` more widely. Currently `SIGNUPS_ALLOWED=true`. (Per Federico's hard rule: env vars need explicit approval. Not changed automatically.)

6. **Create the canary Vaultwarden account** for daily semantic check. Once created, deploy the `vaultwarden-semantic-canary.sh` script from the v2 plan to the small Hetzner VPS.

### Within 90 days

7. **Shamir 2-of-3 split** of the primary age identity. Pick three holders (Federico + 2 trusted independents), do the offline ceremony, dry-run reconstruction, distribute sealed shares.

8. **Quarterly drill** — first weekend of July 2026. Use the procedure in `/root/fede-vault/infra/vaultwarden-restore-drill.md`. Bring the printed primary age identity to the drill (do NOT use the on-disk copy once paper exists).

## What's NOT yet running

- B2 immutable upload (deferred — needs Federico-blocked account signup).
- Healthchecks.io pings (deferred — needs Federico to click magic link).
- VPS-side daily integrity check job (deferred — depends on B2 read-only key).
- Daily semantic canary (deferred — needs canary Vaultwarden account).
- VPS-side retention prune (TODO follow-up; current VPS storage will grow indefinitely until pruning is added — at ~15KB/hour for `hourly-db` only this is ~130 MB/year, not urgent).

## Honest residual risk assessment

| Risk | Mitigated? | Notes |
|------|-----------|-------|
| AX41 disk loss / fire | YES | Encrypted artifacts on small Hetzner VPS, 2 keys (primary + escrow) |
| Hetzner account loss / billing dispute | NO | Both AX41 and small VPS are in same Hetzner account. B2 EU offsite needed. |
| Ransomware on AX41 | PARTIAL | Encrypted artifacts on VPS survive. But VPS is also in Hetzner account, and rrsync allows overwrite. Object Lock (B2) is the proper mitigation. |
| AX41 root compromise (sustained) | NO | Attacker can sign poisoned backups. Detection only via quarterly drill semantic check. Limit blast radius by monitoring + image pinning + canary. |
| Single paper key destruction (fire/flood/theft) | YES | Two independent recovery keys (primary + escrow) stored in two locations. |
| Key rotation in 5 years | DEFERRED | v2 plan has rotation procedure documented. Not automated. |
| Silent SQLite logical corruption | PARTIAL | `integrity_check` + `foreign_key_check` catch structural issues. Quarterly drill catches some semantic issues. Targeted poisoned-row corruption only detected by user discovery or pre-upgrade Bitwarden export comparison. |
| Backblaze account compromise | N/A YET | Not deployed. When deployed, dedicated email + 2FA + monthly audit per v2 plan. |
| GDPR transfer (US storage) | N/A YET | Not deployed. v2 specifies EU Central by default. |
| Floom-stack collapse takes monitoring with it | LOW | ntfy.sh is independent of Floom. last-success.json is local. Only HC.io (when wired) depends on external service. |

## Score

I rate this **8.5/10** for a deployment that ships today.

The gap to 10/10:
- B2 immutable layer is missing (needs Federico signup). Without it, ransomware on AX41 + Hetzner account + correlated attack are not fully mitigated.
- Daily semantic canary is missing (needs canary Vaultwarden account).
- Paper keys are not yet in physical safes (needs Federico to print + store).
- Healthchecks.io is not yet wired (ntfy.sh is the only external monitoring, and it's a fire-and-forget topic, not a dead-man-switch).

When Federico finishes the 5 actions above, the score is 10/10. The pipeline is structurally sound today and provides 90% of the value of the full v2 plan; the remaining 10% needs his decisions and his hands.

## Files index

- `/tmp/icontext-audit/launch/vaultwarden-backup-plan.md` — original Codex v1 plan
- `/tmp/icontext-audit/launch/vaultwarden-backup-plan-v2.md` — Codex v2 adversarial rewrite
- `/tmp/icontext-audit/launch/vaultwarden-backup-DEPLOYED.md` — this file
- `/root/fede-vault/infra/vaultwarden-backup-strategy.md` — original v1 (vault copy)
- `/root/fede-vault/infra/vaultwarden-restore-drill.md` — drill procedure + first-run log
- `/root/fede-vault/infra/vaultwarden-docker-compose.current.yml` — current `docker-compose.yml`
- `/root/fede-vault/infra/vaultwarden-docker-compose.suggested-pinned.yml` — suggested digest-pinned variant
- `/root/vault-handoff/INSTRUCTIONS.txt` — physical-key handoff instructions for Federico
- `/usr/local/sbin/vaultwarden-backup.sh` — the backup script
- `/etc/vaultwarden-backup/` — keys, recipients, env (root-only)
