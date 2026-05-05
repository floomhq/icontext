# Vaultwarden Backup Strategy v2

Status: adversarial rewrite, not implemented.

Scope: Vaultwarden on AX41 at `/opt/vaultwarden`, SQLite data at `/opt/vaultwarden/data`, secondary encrypted copy on the small Hetzner VPS, immutable offsite copy outside Hetzner.

This v2 replaces the weak parts of the original design. The original design protected ciphertext objects well, but it left serious failures in key lifecycle, live attachment consistency, restore-drill realism, B2 account compromise, root-on-AX41 compromise detection, EU privacy posture, and seven-year storage growth.

## Verified External Facts Used

- Backblaze B2 pay-as-you-go storage is billed monthly by byte-hour at `$6.95/TB/30-day` as of the current pricing page.
- Backblaze B2 Object Lock can make objects immutable until a set date; Compliance-mode retention cannot be removed by any user, only extended by clients with the right app key capability.
- Backblaze supports Object Lock retention between 1 and 3,000 days.
- Backblaze Object Lock has no feature fee, but normal storage charges still apply.
- Backblaze B2 offers EU Central storage in Amsterdam. Region selection exists at account creation; Backblaze documentation also states that some account metadata such as account email can reside in the United States.
- SQLite `.backup` uses the SQLite Online Backup API and produces a consistent snapshot of the database file. It does not snapshot Vaultwarden attachment files with the same transaction boundary.
- SQLite `PRAGMA quick_check` skips UNIQUE constraint checks and index/table consistency checks. `PRAGMA integrity_check` is deeper, but it still does not detect application-level poisoned-but-valid Vaultwarden rows.
- `age` supports multiple recipients via repeated `-r` or a recipients file passed with `-R`; any listed recipient can decrypt.

## Adversarial Findings

### 1. Single Points Of Failure

The original plan quietly moved the most important single point of failure from Vaultwarden to a single paper `age` identity. If that paper is burned, stolen, water-damaged, misfiled, or unreadable in five years, every encrypted backup becomes unrecoverable. The stated Shamir 2-of-3 fallback was deferred to v1.1, which means v1 shipped with a known catastrophic recovery dependency and no compensating control.

The Backblaze account is another single point of failure. Object Lock protects existing objects from deletion, but the account owner can still create new buckets, create app keys, run up storage charges, change billing, lose account access, or leave the account locked behind a compromised or inaccessible email identity. The old plan treated B2 as an immutable storage target, not as an account with its own identity, billing, region, and recovery controls.

AX41 root is also a single point of failure for provenance. The AX41 signing key signs whatever AX41 root tells it to sign. A six-month root compromise can produce beautifully signed malicious backups, alter the script, poison manifests, and keep Healthchecks green. Detached signatures only protect against tampering after upload by the VPS or B2; they do not prove the live server was honest at backup time.

### 2. Operational Failure Modes

Cron is a weak scheduler for this job. It does not prevent overlap by default, does not persist missed runs across reboots, gives no native unit-level timeout, does not inhibit shutdown, and produces poor service metadata. On AX41, reboots, package upgrades, clock corrections, and long uploads can create gaps or overlapping hourly/daily runs unless the script has an explicit lock and a persistent scheduler. The original cron entries provided neither.

The original script used SQLite `.backup` correctly for the database, then copied attachments and sends live. That creates a split-brain artifact: the database is from time T, while attachments are from T plus however long `rsync` takes. A user uploading or deleting an attachment during that window can leave a DB row pointing to a missing file, or preserve an orphaned attachment not referenced by the DB. A Vaultwarden container restart or upgrade during the same window makes the artifact even less meaningful.

Tool skew was also unhandled. The plan installed distro `age`, `awscli`, `sqlite3`, and `zstd` without pinning or version checks. An `age` major-version semantic change, an AWS CLI option behavior change, or a SQLite binary with old backup behavior would not be caught until restore. Vaultwarden schema upgrades are another operational failure: if an automatic container update migrates SQLite during the backup window, the backup can capture a valid database for a newer app while the restored compose file pulls a different app image.

### 3. Restore-Drill Failures

The quarterly drill in the old plan was too easy to pass. Starting an isolated container against extracted files verifies that Docker can boot something, but it does not reproduce a real disaster path unless the drill downloads from B2, verifies Object Lock metadata, verifies signatures, decrypts with the offline key, restores onto a fresh host, starts the pinned Vaultwarden image, and exercises the same DNS/TLS/client-access path that a disaster restore uses.

The drill also missed silent attachment loss. Logging in and spot-checking one item does not prove attachments or sends survived. Vaultwarden attachments live as filesystem blobs outside SQLite; a backup can restore the DB perfectly while attachments are absent, stale, or path-mismatched. Without a manifest that records attachment paths, sizes, and hashes, and without a canary attachment that is downloaded through Vaultwarden during drills, attachment failure remains invisible.

The old drill had no downgrade/upgrade validation. A real disaster happens after months of Vaultwarden image changes, schema changes, config changes, and admin-token changes. A drill that reuses the live `/opt/vaultwarden` compose context or pulls `latest` exercises an easier path than disaster recovery. The drill must start from the backed-up compose/env files and pinned image digest, or it is not evidence.

### 4. Encryption Choice

`age` is a reasonable artifact encryption tool for unattended public-key encryption, but the original key story was incomplete. `age` does not give a repository-level key-rotation mechanism like a managed KMS or a backup tool with explicit rekeying. Each old artifact is encrypted to the recipients present at creation time. If Federico rotates the recovery key in 2031, backups created before the rotation remain decryptable only by the old identity unless they are decrypted and re-encrypted into new artifacts.

GPG adds key-expiry and subkey concepts, but it also adds agent behavior, keyring state, packet-format complexity, and more operational footguns. OpenSSL symmetric encryption pushes a long-lived passphrase onto AX41 or into a human ceremony for every backup. Restic with a repo key gives deduplication and easy retention, but an unattended restic repository password on AX41 moves the decrypt boundary online; restic plus Object Lock also has repository lock and prune friction. The right conclusion is not "age solves it"; the right conclusion is "age remains acceptable only with multiple recipients from day one, a written rotation/rewrap procedure, and an explicit admission that old ciphertext cannot be made uncompromised after old-key disclosure."

The old plan also signed only with an online AX41 key. That key proves origin only if AX41 was honest. It does not protect against malicious backups created during host compromise. v2 keeps online signatures for transport tamper detection, but treats them as weak provenance and adds an external semantic canary plus restore drills that detect some classes of valid-but-wrong backups.

### 5. Cost Creep Over 7 Years

The original storage math used a 1 MB artifact and treated 100 MB as a high-end example. That ignores the realistic case: Federico will store passport scans, KYC PDFs, company documents, recovery-code PDFs, and attachment-heavy secure notes. With the old full-artifact-every-hour design, retention creates 10,320 hourly artifacts plus 2,555 daily artifacts, or 12,875 mostly duplicated full copies.

At 2 MB per artifact, 12,875 artifacts consume about 25.1 GB. At 100 MB, they consume about 1.26 TB. At 500 MB, they consume about 6.29 TB. At 2 GB, they consume about 25.15 TB. At the current `$6.95/TB/30-day` B2 rate, that ranges from effectively negligible to about `$175/month` before VAT/currency effects. The old "first 10 GB free" framing fails once attachments grow past toy size.

The fix is retention tiering by data class. Hourly backups carry the database, config, manifests, and small critical files. Daily full backups carry attachments and sends for 430 days. Monthly full backups carry attachments and sends for seven years. This trades attachment RPO from under one hour to under 24 hours for normal operation, with an explicit on-demand full backup command after adding high-value documents.

### 6. Compliance And Privacy

The original plan proposed `us-west-002` without treating jurisdiction as a design choice. Vaultwarden backup artifacts contain personal data and highly sensitive credential-adjacent data, even if the vault payload is encrypted by Bitwarden clients. For a Germany/EU context, storing those artifacts in a US B2 region creates GDPR transfer analysis work, Schrems II/Data Privacy Framework dependency, US legal-access exposure to account metadata, and avoidable privacy optics.

The Cloud Act point is not that Backblaze can decrypt `age` ciphertext; it cannot without the private key. The exposure is metadata and control-plane data: account email, bucket names, object names, object sizes, timestamps, IP logs, billing data, app-key metadata, and access logs. Object names like `vaultwarden/daily/vaultwarden-ax41-daily-20260505T034300Z.tar.zst.age` reveal service identity and cadence. That metadata can be compelled or leaked even when content confidentiality holds.

The fix is to create a new Backblaze account in EU Central, execute Backblaze's DPA for the account, use opaque bucket and object prefixes, keep object names service-neutral, and minimize account metadata. If a US provider is retained, the plan must record the GDPR basis and accept the residual metadata risk. v2 uses EU Central by default.

### 7. Recursive Problem: Paper Key In Safe

The paper-key safe plan is a classic recursive recovery failure. If the safe is destroyed in the same fire/flood/burglary that destroys local machines and documents, the encrypted backups survive but the decrypt capability does not. A safe deposit box lowers home-disaster correlation, but introduces bank access, death/incapacity, and paperwork failure modes.

Deferring Shamir was not acceptable. The operational risk of a Shamir ceremony is real: bad transcription, confused share labels, a malicious or careless holder, and recovery delays. But those risks can be reduced with a dry-run reconstruction, sealed instructions, and independent holder selection. The catastrophic single-paper risk has no mitigation after the paper is gone.

v2 requires two independent recovery paths before production: one complete printed `age` identity in a fire-rated location and a tested 2-of-3 Shamir split stored with three separate holders. The Shamir split is not a future enhancement; it is a launch gate.

### 8. Backblaze Account Compromise

If the Backblaze login uses `depontefede@gmail.com`, Gmail compromise can become B2 compromise. Object Lock blocks deletion of locked objects, but it does not block account abuse. An attacker can create buckets, upload junk forever, create new app keys, change billing state, enumerate object metadata, disable lifecycle on unlocked objects, and use the account as a foothold for social engineering.

Restricted application keys do not solve account compromise because the console owner can mint new keys. The mitigation has to be at the account identity and billing layers: separate Backblaze account, separate email identity, phishing-resistant 2FA, printed recovery codes, payment controls, provider alerts, and a monthly independent account audit from a read-only lane.

v2 also makes object names opaque. Even if an attacker gets metadata, they get less semantic value from bucket and key names. That does not stop billing abuse, but it reduces privacy leakage from object inventory.

### 9. Subtle Attacks From AX41 Root

An attacker with AX41 root for six months wins more than the old plan admitted. They can read the live SQLite database, admin token, compose file, B2 write key, Healthchecks URLs, and signing key. They can sign malicious backups, keep `quick_check` green, alter the backup script to omit attachments, fake manifest counts, block alerts, and restore old known-good canary data while poisoning real rows.

Retention and restore drills mitigate only part of that. With monthly remote metadata checks, detection of missing B2 objects is within about one month. With daily semantic canary checks from the VPS, detection of a broken canary path is within 24 hours. With quarterly real-account restore drills, detection of broad semantic corruption is within 100 days. None of those catch a targeted valid-but-wrong cipher row until Federico or a real client uses that item and notices.

The fix is to stop overclaiming. v2 calls AX41 root compromise a catastrophic event that invalidates all backups produced during the compromise window unless external evidence narrows the blast radius. It adds off-host canary checks, version and count ledgers, signed script hashes, and mandatory manual review after suspected compromise, but it does not pretend checksums prove application truth.

### 10. Silent SQLite And Logical Corruption

`PRAGMA quick_check` is insufficient, and the original plan already ran `integrity_check`, but even `integrity_check` only validates SQLite structure and constraints. It does not know Vaultwarden semantics. A compromised Vaultwarden binary can write valid SQLite rows with wrong encrypted payloads, delete ciphers cleanly, rewrite attachment references, or preserve counts while corrupting contents. Hashes and signatures then faithfully preserve the poison.

The realistic failure is not a malformed database. The realistic failure is valid data that Vaultwarden can read but humans cannot trust: missing organization items, stale attachments, replaced TOTP seeds, altered URLs, or deleted recovery notes. A quarterly container boot does not catch that unless the drill verifies specific high-value items and attachments by name through a real client path.

v2 adds three semantic controls: a dedicated canary account checked daily from the VPS through Vaultwarden, a quarterly real-account restore drill with an offline checklist of high-value item titles and attachment names, and a manual encrypted Bitwarden export before Vaultwarden image upgrades. These controls do not prove every secret is correct, but they catch classes of silent logical corruption that SQLite cannot see.

## Top 5 Concrete Fixes

1. Replace cron with systemd timers and a locked, shutdown-inhibited service. Use `flock`, `Persistent=true`, explicit timeouts, version gates, and controlled stop/snapshot/start of Vaultwarden.
2. Make recovery-key redundancy a launch gate. Use one primary `age` identity, one escrow `age` identity, and tested Shamir 2-of-3 for the primary identity before production.
3. Move B2 to a dedicated EU Central account with phishing-resistant 2FA, separate email, DPA, opaque names, restricted write-only backup key, billing controls, and monthly account audit.
4. Replace theatre drills with real disaster drills: download from B2, verify object lock, verify signatures, decrypt with offline key, restore onto a fresh host, start the pinned image, test login, canary item, and canary attachment.
5. Split retention by data class to stop seven-year attachment duplication. Hourly DB/config artifacts retain 430 days; daily full artifacts retain 430 days; monthly full artifacts retain 2,555 days. Run on-demand full backup after adding critical documents.

## Decision

Use immutable, self-contained encrypted artifacts as the primary backup unit, but split backup modes by data class:

- `hourly-db`: SQLite snapshot, Vaultwarden config, RSA keys, admin hash/config files, compose files, wrappers, semantic manifests. No attachments or sends except their path/hash manifest. Retain 430 days.
- `daily-full`: Everything in `hourly-db` plus attachments and sends. Retain 430 days.
- `monthly-full`: Everything in `daily-full`. Retain 2,555 days.
- `manual-full`: Same as `daily-full`, run immediately after Federico stores high-value documents such as passport scans, KYC packs, recovery-code PDFs, or legal documents.

Pipeline:

1. A systemd service obtains an exclusive lock and delays shutdown while running.
2. The service records tool versions and the pinned Vaultwarden image digest.
3. The service stops Vaultwarden with a bounded timeout unless running in explicit `online-db-only` emergency mode.
4. AX41 creates a SQLite `.backup`, copies restore-critical files, copies attachments/sends for full modes, records attachment path/size/hash manifests, and restarts Vaultwarden.
5. The service runs SQLite `integrity_check`, `foreign_key_check`, and Vaultwarden schema/count queries on the copied database.
6. The service creates a deterministic `tar.zst`, encrypts with `age >=1.2,<2` to all recipients in `/etc/vaultwarden-backup/age-recipients`, signs the encrypted artifact with the AX41 OpenSSH signing key, and writes SHA-256 sidecars.
7. AX41 uploads encrypted artifacts to:
   - a small Hetzner VPS for fast host-loss recovery,
   - a dedicated Backblaze B2 EU Central Object Lock bucket in Compliance mode for immutable offsite retention.
8. Healthchecks monitors every scheduled run. A separate VPS semantic canary checks the live service daily. Quarterly drills exercise the real disaster path.

This gives:

- AX41 death: restore from VPS or B2.
- Small VPS death: restore from B2.
- Hetzner account loss: B2 remains outside the Hetzner account.
- Accidental deletion/corruption: timestamped versions with database history for 430 days and full attachment history daily/monthly.
- Ransomware on AX41: B2 Object Lock blocks deletion or overwrite of locked history.
- B2 storage compromise without key compromise: attacker gets ciphertext plus metadata.
- AX41 root compromise: treated as catastrophic for backups generated during compromise; external canaries and drills bound some detection windows but do not prove all secrets remain correct.

## 3-2-1 Application

Copies:

1. Primary live data: `/opt/vaultwarden/data` on AX41.
2. Secondary copy: encrypted artifacts on the small Hetzner VPS.
3. True offsite copy: encrypted immutable artifacts in Backblaze B2 EU Central.

Media/control planes:

- AX41 local disk.
- Small VPS disk in the same provider family but a separate host.
- Backblaze B2 object storage in a separate account, separate provider, EU Central region.

Offsite:

- The small Hetzner VPS is not a true offsite control-plane copy because it shares Hetzner account/provider risk.
- Backblaze B2 EU Central is the required offsite copy.
- Hetzner Storage Box remains a possible extra copy, not the required offsite copy.

## What To Back Up

Every `hourly-db`, `daily-full`, `monthly-full`, and `manual-full` run backs up:

- `/opt/vaultwarden/data/db.sqlite3` via `.backup` only.
- `/opt/vaultwarden/data/rsa_key.pem`, `rsa_key.der`, `rsa_key.pub.der`, `rsa_key.pub.pem` if present.
- `/opt/vaultwarden/data/config.json` if present.
- `/opt/vaultwarden/docker-compose.yml`.
- `/opt/vaultwarden/.env` if present.
- `/opt/vaultwarden/migrate-secrets.py` if present.
- `/opt/vaultwarden/migration-log.json` if present.
- `/opt/vaultwarden/wrappers/` if present.
- Manifest files generated by the backup job:
  - `MANIFEST.json`
  - `MANIFEST.sha256`
  - `ATTACHMENTS.tsv`
  - `SENDS.tsv`
  - `TOOL-VERSIONS.txt`
  - `RESTORE-NOTES.txt`

Only `daily-full`, `monthly-full`, and `manual-full` include file payloads:

- `/opt/vaultwarden/data/attachments/` if present.
- `/opt/vaultwarden/data/sends/` if present.

Do not back up as authoritative state:

- `db.sqlite3-wal` and `db.sqlite3-shm` from the live directory. The `.backup` output is the database snapshot. During restore, remove stale `-wal` and `-shm` before starting Vaultwarden.
- `icon_cache/`; it is cache.

Immediate hardening adjacent to backup:

- Set `SIGNUPS_ALLOWED=false` before exposing `vault.floom.dev`.
- Replace plaintext `ADMIN_TOKEN` with an Argon2 PHC hash in `.env`.
- Remove any separate plaintext `/opt/vaultwarden/data/admin-token` file after confirming the hashed env token works.
- Pin Vaultwarden by explicit tag and digest. Do not use `vaultwarden/server:latest` or Watchtower-style automatic upgrades.
- Add a manual pre-upgrade backup gate: run `vaultwarden-backup.sh manual-full` before changing the Vaultwarden image.

## Encryption, Signing, And Key Lifecycle

Primary encryption: `age` public-key encryption, pinned to `age >=1.2,<2`.

Reason:

- AX41 only needs public recipients for unattended encryption.
- No backup decryption secret lives in Vaultwarden.
- Restore requires offline identity material, which is the intended boundary.
- Multiple recipients are simple and explicit.

Signing: OpenSSH detached signatures over the encrypted artifact with an AX41-only signing key.

Reason:

- The small VPS cannot forge replacement artifacts.
- B2 cannot forge replacement artifacts.
- Restore verifies SHA-256 and AX41 signature before decrypting.

Important limit:

- AX41 root can sign malicious backups. Signatures are transport provenance, not proof of semantic truth.

Not selected as primary:

- GPG: higher keyring/agent complexity for this unattended pipeline.
- OpenSSL symmetric encryption: either puts a decryption passphrase online or requires manual encryption for every run.
- Restic native as source of truth: good deduplication, but the repo key would be online for unattended backups and restic prune/locks are awkward against WORM retention.
- Borg native: strong for append-only SSH, but still creates key/passphrase lifecycle work and is unnecessary for the DB/config tier.
- Vaultwarden admin export: useful semantic layer, not a server restore.

### Required Key Ceremony

Create two `age` identities offline:

```bash
install -d -m 0700 ./vw-key-ceremony
cd ./vw-key-ceremony

age-keygen -o vaultwarden-backup-primary-age-identity-2026Q2.txt
age-keygen -y vaultwarden-backup-primary-age-identity-2026Q2.txt > vaultwarden-backup-primary-age-recipient-2026Q2.txt

age-keygen -o vaultwarden-backup-escrow-age-identity-2026Q2.txt
age-keygen -y vaultwarden-backup-escrow-age-identity-2026Q2.txt > vaultwarden-backup-escrow-age-recipient-2026Q2.txt

cat vaultwarden-backup-primary-age-recipient-2026Q2.txt \
    vaultwarden-backup-escrow-age-recipient-2026Q2.txt \
  > age-recipients-2026Q2.txt
```

Print:

- Primary identity.
- Escrow identity.
- Recipients file.
- AX41 backup signing public key and allowed signers line.
- B2 account recovery instructions.

Store:

- Primary identity in Federico's fire-rated safe or safe deposit box.
- Escrow identity with a different physical custodian/location.
- Recipients file on AX41 at `/etc/vaultwarden-backup/age-recipients`.

Install recipients on AX41:

```bash
install -d -m 0700 /etc/vaultwarden-backup
install -m 0444 age-recipients-2026Q2.txt /etc/vaultwarden-backup/age-recipients
```

### Shamir 2-of-3 Launch Gate

Install `ssss` from distro packages only for the offline ceremony:

```bash
apt-get update
apt-get install -y ssss
```

Split the primary identity:

```bash
grep '^AGE-SECRET-KEY-1' vaultwarden-backup-primary-age-identity-2026Q2.txt > vaultwarden-backup-primary-age-secret-line-2026Q2.txt
ssss-split -t 2 -n 3 -w vw-age-2026Q2 < vaultwarden-backup-primary-age-secret-line-2026Q2.txt
```

Recovery dry run:

```bash
ssss-combine -t 2 > reconstructed-primary-age-identity-2026Q2.txt
diff -u vaultwarden-backup-primary-age-secret-line-2026Q2.txt reconstructed-primary-age-identity-2026Q2.txt
age-keygen -y reconstructed-primary-age-identity-2026Q2.txt
```

The printed shares go to three independent holders. The sealed instructions include:

- Required threshold: any 2 of 3 shares.
- Exact `ssss-combine -t 2` command.
- The expected public recipient string from `vaultwarden-backup-primary-age-recipient-2026Q2.txt`.
- A warning that a single share is not enough and must not be photographed or stored in Vaultwarden.

### Key Rotation Procedure

Rotation for planned lifecycle every 24 months:

1. Generate a new primary and escrow identity offline.
2. Create a new recipients file containing old and new recipients for a 90-day overlap.
3. Install the new recipients file on AX41.
4. Run `manual-full` and verify restore with the new identity.
5. After 90 days, remove old recipients from future backups.
6. Keep old private identities until every backup encrypted to them has expired or has been rewrapped.

Commands:

```bash
cd ./vw-key-ceremony

age-keygen -o vaultwarden-backup-primary-age-identity-2028Q2.txt
age-keygen -y vaultwarden-backup-primary-age-identity-2028Q2.txt > vaultwarden-backup-primary-age-recipient-2028Q2.txt

age-keygen -o vaultwarden-backup-escrow-age-identity-2028Q2.txt
age-keygen -y vaultwarden-backup-escrow-age-identity-2028Q2.txt > vaultwarden-backup-escrow-age-recipient-2028Q2.txt

cat vaultwarden-backup-primary-age-recipient-2026Q2.txt \
    vaultwarden-backup-escrow-age-recipient-2026Q2.txt \
    vaultwarden-backup-primary-age-recipient-2028Q2.txt \
    vaultwarden-backup-escrow-age-recipient-2028Q2.txt \
  > age-recipients-rotation-overlap-2028Q2.txt

install -m 0444 age-recipients-rotation-overlap-2028Q2.txt /etc/vaultwarden-backup/age-recipients
/usr/local/sbin/vaultwarden-backup.sh manual-full
```

Rewrap selected old artifacts to new recipients on an offline restore workstation:

```bash
export OLD_ID='./vaultwarden-backup-primary-age-identity-2026Q2.txt'
export NEW_RECIPIENTS='./age-recipients-2028Q2-only.txt'
export BASE='OBJECT_BASENAME.tar.zst.age'

sha256sum -c "$BASE.sha256"
ssh-keygen -Y verify \
  -f ./allowed_signers \
  -I vaultwarden-backup@ax41 \
  -n vaultwarden-backup \
  -s "$BASE.sig" < "$BASE"

age -d -i "$OLD_ID" "$BASE" \
  | age -R "$NEW_RECIPIENTS" -o "$BASE.rewrapped-2028Q2.age"

sha256sum "$BASE.rewrapped-2028Q2.age" > "$BASE.rewrapped-2028Q2.age.sha256"
ssh-keygen -Y sign \
  -f ./offline_rewrap_signing_key \
  -n vaultwarden-backup-rewrap \
  "$BASE.rewrapped-2028Q2.age"
```

Upload rewrapped objects under `r/<opaque-run-id>/...` with their own Object Lock retention. Do not overwrite locked originals. If an old private key is disclosed, assume all ciphertext ever encrypted to it is disclosed if an attacker obtained object access; rewrapping after disclosure cannot erase copies already taken.

## Storage Target Decision

Primary offsite target: Backblaze B2 EU Central with Object Lock enabled in Compliance mode.

Account requirements:

- Dedicated Backblaze account, not the normal Gmail identity.
- Email address protected by hardware security key or phishing-resistant 2FA.
- Unique passphrase stored in the paper recovery pack and not in Vaultwarden.
- Backblaze DPA accepted for the account.
- Recovery codes printed and stored with the recovery pack.
- Billing card with monthly spending controls where available.
- Backblaze alert emails routed to Federico and one secondary mailbox.

Bucket naming:

- Do not use `vaultwarden`, `password`, `backup`, `fede`, or domain names in the bucket name.
- Use an opaque bucket name such as `bb-euc-7m4q2r-worm`.
- Use opaque prefixes:
  - `h/` for hourly database artifacts.
  - `d/` for daily full artifacts.
  - `m/` for monthly full artifacts.
  - `r/` for rewrapped artifacts.

Cost model:

- Hourly DB/config artifact assumed at 2 MB after compression: `10,320 * 2 MB = 20.6 GB`.
- Daily/monthly full attachment artifact count: `430 daily + 84 monthly = 514`.
- Full artifact storage:
  - 100 MB attachments: about 51.4 GB.
  - 500 MB attachments: about 257 GB.
  - 2 GB attachments: about 1.03 TB.
  - 10 GB attachments: about 5.14 TB.
- At `$6.95/TB/30-day`, 2 GB of attachment payload retained under v2 costs about `$7/month` for full tiers, plus DB tier. The old hourly-full design at 2 GB would have cost about `$175/month`.

Storage policy:

- If attachment payload exceeds 2 GB, review retention and monthly cost before continuing unchanged.
- If attachment payload exceeds 10 GB, move attachments/sends to a dedicated deduplicated backup design and keep this artifact design for DB/config.
- Run `/usr/local/sbin/vaultwarden-backup.sh manual-full` immediately after uploading high-value documents.

## Schedule

Use UTC.

- `hourly-db`: minute 17 of every hour. RPO for vault database/config is under 1 hour.
- `daily-full`: 03:43 UTC daily. RPO for attachments/sends is under 24 hours.
- `monthly-full`: 04:11 UTC on the first day of each month. Seven-year full retention.
- `manual-full`: on demand after high-value document additions and before Vaultwarden upgrades.
- Remote B2 object/signature/retention check from the small VPS: daily at 05:29 UTC.
- Semantic canary check from the small VPS: daily at 06:07 UTC.
- Quarterly full restore drill: first weekend of January, April, July, October.

## Retention

B2 immutable:

- `h/`: hourly DB/config artifacts, 430 days, Compliance mode.
- `d/`: daily full artifacts, 430 days, Compliance mode.
- `m/`: monthly full artifacts, 2,555 days, Compliance mode.
- `r/`: rewrapped artifacts, retention equal to or longer than the source artifact's remaining retention.

Small VPS:

- Hourly DB/config: 30 days.
- Daily full: 90 days.
- Monthly full: 24 months.

Detection-window truth:

- Missing scheduled backups: Healthchecks detects in 30 minutes to 2 hours depending on mode.
- Missing B2 uploads or object-lock metadata failure: daily remote check detects within 24 hours.
- Canary account/app path corruption: daily semantic check detects within 24 hours if the canary path is affected.
- Broad restore breakage: quarterly drill detects within 100 days.
- Targeted valid-but-wrong user cipher corruption: only user discovery, manual real-account drill, or pre-upgrade/manual export comparison catches it.

## AX41 Setup Commands

Install tools:

```bash
apt-get update
apt-get install -y sqlite3 zstd curl ca-certificates openssh-client jq rsync util-linux coreutils docker.io docker-compose-plugin
```

Install `age >=1.2,<2` from the official release package or a distro package that satisfies the constraint. Verify:

```bash
age --version
sqlite3 --version
zstd --version
aws --version
docker compose version
```

Install AWS CLI v2.15 or newer:

```bash
curl -fsSLo /tmp/awscliv2.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip
cd /tmp
unzip -q awscliv2.zip
./aws/install --update
aws --version
```

Create directories:

```bash
install -d -m 0700 /etc/vaultwarden-backup
install -d -m 0700 /var/backups/vaultwarden/hourly-db
install -d -m 0700 /var/backups/vaultwarden/daily-full
install -d -m 0700 /var/backups/vaultwarden/monthly-full
install -d -m 0700 /var/lib/vaultwarden-backup
install -d -m 0700 /var/log/vaultwarden-backup
```

Create the signing key on AX41:

```bash
ssh-keygen -t ed25519 -N '' -C vaultwarden-backup@ax41 -f /etc/vaultwarden-backup/signing_key
chmod 0400 /etc/vaultwarden-backup/signing_key
ssh-keygen -y -f /etc/vaultwarden-backup/signing_key > /etc/vaultwarden-backup/signing_key.pub
chmod 0444 /etc/vaultwarden-backup/signing_key.pub
printf 'vaultwarden-backup@ax41 %s\n' "$(cat /etc/vaultwarden-backup/signing_key.pub)" > /etc/vaultwarden-backup/allowed_signers
chmod 0444 /etc/vaultwarden-backup/allowed_signers
```

Create B2 bucket with Object Lock enabled in the dedicated EU Central account:

```bash
export AWS_ACCESS_KEY_ID='<B2 setup key id with bucket admin permission>'
export AWS_SECRET_ACCESS_KEY='<B2 setup application key>'
export AWS_DEFAULT_REGION='eu-central-003'
export B2_ENDPOINT_URL='https://s3.eu-central-003.backblazeb2.com'
export B2_BUCKET='bb-euc-7m4q2r-worm'

aws s3api create-bucket \
  --bucket "$B2_BUCKET" \
  --object-lock-enabled-for-bucket \
  --endpoint-url "$B2_ENDPOINT_URL"
```

Set a default 430-day Compliance retention as a safety net:

```bash
aws s3api put-object-lock-configuration \
  --bucket "$B2_BUCKET" \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "COMPLIANCE",
        "Days": 430
      }
    }
  }'
```

Create a restricted B2 application key for AX41:

- Bucket: `bb-euc-7m4q2r-worm`.
- Capabilities: list bucket, list files, read files, write files, write file retentions.
- No delete capability.
- No bucket creation capability.
- No key creation capability.

Create `/etc/vaultwarden-backup/backup.env`:

```bash
install -m 0600 /dev/null /etc/vaultwarden-backup/backup.env
editor /etc/vaultwarden-backup/backup.env
```

Content:

```bash
export AWS_ACCESS_KEY_ID='REPLACE_WITH_RESTRICTED_B2_KEY_ID'
export AWS_SECRET_ACCESS_KEY='REPLACE_WITH_RESTRICTED_B2_APPLICATION_KEY'
export AWS_DEFAULT_REGION='eu-central-003'
export AWS_EC2_METADATA_DISABLED='true'

B2_ENDPOINT_URL='https://s3.eu-central-003.backblazeb2.com'
B2_BUCKET='bb-euc-7m4q2r-worm'

VW_DATA='/opt/vaultwarden/data'
VW_ROOT='/opt/vaultwarden'
VW_CONTAINER='vaultwarden'
AGE_RECIPIENTS_FILE='/etc/vaultwarden-backup/age-recipients'
SIGNING_KEY='/etc/vaultwarden-backup/signing_key'
LOCAL_BACKUP_ROOT='/var/backups/vaultwarden'
REMOTE_VPS='hetzner'
REMOTE_VPS_DIR='/srv/backups/vaultwarden'

HEALTHCHECKS_HOURLY_DB_URL='https://hc-ping.com/REPLACE_HOURLY_DB_UUID'
HEALTHCHECKS_DAILY_FULL_URL='https://hc-ping.com/REPLACE_DAILY_FULL_UUID'
HEALTHCHECKS_MONTHLY_FULL_URL='https://hc-ping.com/REPLACE_MONTHLY_FULL_UUID'
HEALTHCHECKS_MANUAL_FULL_URL='https://hc-ping.com/REPLACE_MANUAL_FULL_UUID'
```

## Backup Script

Write `/usr/local/sbin/vaultwarden-backup.sh` with mode `0750`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

MODE="${1:-hourly-db}"
case "$MODE" in
  hourly-db|daily-full|monthly-full|manual-full) ;;
  *) echo "usage: $0 hourly-db|daily-full|monthly-full|manual-full" >&2; exit 64 ;;
esac

source /etc/vaultwarden-backup/backup.env

case "$MODE" in
  hourly-db) HC_URL="$HEALTHCHECKS_HOURLY_DB_URL"; RETENTION_DAYS=430; PREFIX='h' ;;
  daily-full) HC_URL="$HEALTHCHECKS_DAILY_FULL_URL"; RETENTION_DAYS=430; PREFIX='d' ;;
  monthly-full) HC_URL="$HEALTHCHECKS_MONTHLY_FULL_URL"; RETENTION_DAYS=2555; PREFIX='m' ;;
  manual-full) HC_URL="$HEALTHCHECKS_MANUAL_FULL_URL"; RETENTION_DAYS=2555; PREFIX='m' ;;
esac

LOCK=/run/vaultwarden-backup.lock
exec 9>"$LOCK"
flock -n 9

WORK="$(mktemp -d /var/tmp/vw-backup.XXXXXX)"
VW_WAS_RUNNING=0
cleanup() { rm -rf "$WORK"; }
restart_vw() {
  if [ "$VW_WAS_RUNNING" = "1" ]; then
    (cd "$VW_ROOT" && docker compose up -d)
  fi
}
fail() {
  rc=$?
  restart_vw >/dev/null 2>&1 || true
  curl -fsS -m 10 --retry 3 "$HC_URL/fail" >/dev/null 2>&1 || true
  cleanup
  exit "$rc"
}
trap fail ERR
trap cleanup EXIT

curl -fsS -m 10 --retry 3 "$HC_URL/start" >/dev/null 2>&1 || true

for bin in sqlite3 age zstd tar sha256sum aws ssh-keygen rsync curl find awk sed jq docker flock systemd-inhibit; do
  command -v "$bin" >/dev/null
done

AGE_VER="$(age --version | awk '{print $NF}')"
case "$AGE_VER" in
  1.*|v1.*) ;;
  *) echo "unsupported age version: $AGE_VER" >&2; exit 70 ;;
esac

AWS_VER="$(aws --version 2>&1)"
SQLITE_VER="$(sqlite3 --version)"
ZSTD_VER="$(zstd --version)"
DOCKER_COMPOSE_VER="$(docker compose version)"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
EPOCH="$(date -u +%s)"
HOST="$(hostname -f 2>/dev/null || hostname)"
RUN_ID="$(printf '%s-%s-%s' "$MODE" "$TS" "$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 10)")"
STAGE="$WORK/stage"
OUTDIR="$LOCAL_BACKUP_ROOT/$MODE"
BASE="${RUN_ID}"
ARTIFACT="$OUTDIR/${BASE}.tar.zst.age"

install -d -m 0700 "$STAGE/data" "$STAGE/opt/vaultwarden" "$OUTDIR"

if docker inspect "$VW_CONTAINER" >/dev/null 2>&1; then
  if [ "$(docker inspect -f '{{.State.Running}}' "$VW_CONTAINER")" = "true" ]; then
    VW_WAS_RUNNING=1
    (cd "$VW_ROOT" && docker compose stop -t 30 "$VW_CONTAINER")
  fi
fi

sqlite3 "$VW_DATA/db.sqlite3" ".timeout 5000" ".backup '$STAGE/data/db.sqlite3'"
test "$(sqlite3 "$STAGE/data/db.sqlite3" 'PRAGMA integrity_check;')" = "ok"
test -z "$(sqlite3 "$STAGE/data/db.sqlite3" 'PRAGMA foreign_key_check;' 2>/dev/null)"

for f in rsa_key.pem rsa_key.der rsa_key.pub.der rsa_key.pub.pem config.json; do
  [ -f "$VW_DATA/$f" ] && cp -a "$VW_DATA/$f" "$STAGE/data/$f"
done

for p in docker-compose.yml .env migrate-secrets.py migration-log.json; do
  [ -f "$VW_ROOT/$p" ] && cp -a "$VW_ROOT/$p" "$STAGE/opt/vaultwarden/$p"
done

[ -d "$VW_ROOT/wrappers" ] && rsync -a "$VW_ROOT/wrappers/" "$STAGE/opt/vaultwarden/wrappers/"

find "$VW_DATA/attachments" -type f -printf '%P\t%s\t' -exec sha256sum {} \; 2>/dev/null \
  | awk -F '\t|  ' '{print $1 "\t" $2 "\t" $3}' | sort > "$STAGE/ATTACHMENTS.tsv" || true
find "$VW_DATA/sends" -type f -printf '%P\t%s\t' -exec sha256sum {} \; 2>/dev/null \
  | awk -F '\t|  ' '{print $1 "\t" $2 "\t" $3}' | sort > "$STAGE/SENDS.tsv" || true

case "$MODE" in
  daily-full|monthly-full|manual-full)
    [ -d "$VW_DATA/attachments" ] && rsync -a "$VW_DATA/attachments/" "$STAGE/data/attachments/"
    [ -d "$VW_DATA/sends" ] && rsync -a "$VW_DATA/sends/" "$STAGE/data/sends/"
    ;;
esac

IMAGE_ID="$(docker inspect -f '{{.Image}}' "$VW_CONTAINER" 2>/dev/null || true)"
IMAGE_DIGEST=""
if [ -n "$IMAGE_ID" ]; then
  IMAGE_DIGEST="$(docker image inspect --format='{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' "$IMAGE_ID" 2>/dev/null || true)"
fi

restart_vw
VW_WAS_RUNNING=0

USER_COUNT="$(sqlite3 "$STAGE/data/db.sqlite3" 'SELECT COUNT(*) FROM users;')"
CIPHER_COUNT="$(sqlite3 "$STAGE/data/db.sqlite3" 'SELECT COUNT(*) FROM ciphers;')"
ATTACHMENT_COUNT="$(wc -l < "$STAGE/ATTACHMENTS.tsv" 2>/dev/null || echo 0)"
ATTACHMENT_BYTES="$(awk '{sum += $2} END {print sum+0}' "$STAGE/ATTACHMENTS.tsv" 2>/dev/null || echo 0)"
SEND_COUNT="$(wc -l < "$STAGE/SENDS.tsv" 2>/dev/null || echo 0)"
SEND_BYTES="$(awk '{sum += $2} END {print sum+0}' "$STAGE/SENDS.tsv" 2>/dev/null || echo 0)"

cat >"$STAGE/TOOL-VERSIONS.txt" <<EOF
age=$AGE_VER
aws=$AWS_VER
sqlite=$SQLITE_VER
zstd=$ZSTD_VER
docker_compose=$DOCKER_COMPOSE_VER
vaultwarden_image_digest=$IMAGE_DIGEST
EOF

jq -n \
  --arg created_utc "$TS" \
  --arg source_host "$HOST" \
  --arg mode "$MODE" \
  --arg run_id "$RUN_ID" \
  --arg vaultwarden_root "$VW_ROOT" \
  --arg vaultwarden_data "$VW_DATA" \
  --arg image_digest "$IMAGE_DIGEST" \
  --argjson user_count "$USER_COUNT" \
  --argjson cipher_count "$CIPHER_COUNT" \
  --argjson attachment_count "$ATTACHMENT_COUNT" \
  --argjson attachment_bytes "$ATTACHMENT_BYTES" \
  --argjson send_count "$SEND_COUNT" \
  --argjson send_bytes "$SEND_BYTES" \
  '{
    created_utc: $created_utc,
    source_host: $source_host,
    mode: $mode,
    run_id: $run_id,
    vaultwarden_root: $vaultwarden_root,
    vaultwarden_data: $vaultwarden_data,
    vaultwarden_image_digest: $image_digest,
    sqlite_integrity_check: "ok",
    sqlite_foreign_key_check: "ok",
    user_count: $user_count,
    cipher_count: $cipher_count,
    attachment_count: $attachment_count,
    attachment_bytes: $attachment_bytes,
    send_count: $send_count,
    send_bytes: $send_bytes
  }' > "$STAGE/MANIFEST.json"

cat >"$STAGE/RESTORE-NOTES.txt" <<EOF
Restore notes:
1. Verify SHA-256 and OpenSSH signature before decrypting.
2. Decrypt with an offline age identity listed in the recovery pack.
3. Stop Vaultwarden before replacing files.
4. Restore data/db.sqlite3 as /opt/vaultwarden/data/db.sqlite3.
5. Restore attachments and sends only from a full artifact or a selected full artifact plus newer manual-full artifact.
6. Delete stale /opt/vaultwarden/data/db.sqlite3-wal and db.sqlite3-shm before start.
7. Restore rsa_key.* with the database.
8. Start the pinned Vaultwarden image digest recorded in TOOL-VERSIONS.txt unless a deliberate upgrade restore is being tested.
EOF

(cd "$STAGE" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256)

tar --sort=name --mtime="@$EPOCH" --owner=0 --group=0 --numeric-owner -C "$STAGE" -cf - . \
  | zstd -T1 -10 \
  | age -R "$AGE_RECIPIENTS_FILE" -o "$ARTIFACT"

(cd "$OUTDIR" && sha256sum "$(basename "$ARTIFACT")" > "$(basename "$ARTIFACT").sha256")
ssh-keygen -Y sign -f "$SIGNING_KEY" -n vaultwarden-backup "$ARTIFACT" >/dev/null

RETAIN_UNTIL="$(date -u -d "+${RETENTION_DAYS} days" '+%Y-%m-%dT%H:%M:%SZ')"
for f in "$ARTIFACT" "$ARTIFACT.sha256" "$ARTIFACT.sig"; do
  key="${PREFIX}/${BASE}/$(basename "$f")"
  aws s3api put-object \
    --bucket "$B2_BUCKET" \
    --key "$key" \
    --body "$f" \
    --object-lock-mode COMPLIANCE \
    --object-lock-retain-until-date "$RETAIN_UNTIL" \
    --endpoint-url "$B2_ENDPOINT_URL" >/dev/null
  aws s3api head-object \
    --bucket "$B2_BUCKET" \
    --key "$key" \
    --endpoint-url "$B2_ENDPOINT_URL" >/dev/null
done

rsync -a --ignore-existing "$ARTIFACT" "$ARTIFACT.sha256" "$ARTIFACT.sig" \
  "$REMOTE_VPS:$REMOTE_VPS_DIR/$MODE/"

find "$LOCAL_BACKUP_ROOT/hourly-db" -type f -mtime +30 -delete 2>/dev/null || true
find "$LOCAL_BACKUP_ROOT/daily-full" -type f -mtime +90 -delete 2>/dev/null || true
find "$LOCAL_BACKUP_ROOT/monthly-full" -type f -mtime +730 -delete 2>/dev/null || true

jq -n \
  --arg created_utc "$TS" \
  --arg mode "$MODE" \
  --arg artifact "$(basename "$ARTIFACT")" \
  --arg b2_retention_until "$RETAIN_UNTIL" \
  --argjson user_count "$USER_COUNT" \
  --argjson cipher_count "$CIPHER_COUNT" \
  --argjson attachment_count "$ATTACHMENT_COUNT" \
  --argjson attachment_bytes "$ATTACHMENT_BYTES" \
  '{
    created_utc: $created_utc,
    mode: $mode,
    artifact: $artifact,
    b2_retention_until: $b2_retention_until,
    user_count: $user_count,
    cipher_count: $cipher_count,
    attachment_count: $attachment_count,
    attachment_bytes: $attachment_bytes
  }' > /var/lib/vaultwarden-backup/last-success.json

curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
```

Install it:

```bash
install -m 0750 vaultwarden-backup.sh /usr/local/sbin/vaultwarden-backup.sh
```

## systemd Units

Create `/etc/systemd/system/vaultwarden-backup@.service`:

```ini
[Unit]
Description=Vaultwarden backup (%i)
Wants=network-online.target docker.service
After=network-online.target docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/systemd-inhibit --what=shutdown:sleep --mode=delay --who=vaultwarden-backup --why="Vaultwarden backup in progress" /usr/local/sbin/vaultwarden-backup.sh %i
TimeoutStartSec=30m
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
```

Create `/etc/systemd/system/vaultwarden-backup-hourly-db.timer`:

```ini
[Unit]
Description=Hourly Vaultwarden DB/config backup

[Timer]
OnCalendar=*-*-* *:17:00 UTC
Persistent=true
RandomizedDelaySec=90
Unit=vaultwarden-backup@hourly-db.service

[Install]
WantedBy=timers.target
```

Create `/etc/systemd/system/vaultwarden-backup-daily-full.timer`:

```ini
[Unit]
Description=Daily Vaultwarden full backup

[Timer]
OnCalendar=*-*-* 03:43:00 UTC
Persistent=true
RandomizedDelaySec=120
Unit=vaultwarden-backup@daily-full.service

[Install]
WantedBy=timers.target
```

Create `/etc/systemd/system/vaultwarden-backup-monthly-full.timer`:

```ini
[Unit]
Description=Monthly Vaultwarden full backup

[Timer]
OnCalendar=*-*-01 04:11:00 UTC
Persistent=true
RandomizedDelaySec=180
Unit=vaultwarden-backup@monthly-full.service

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl daemon-reload
systemctl enable --now vaultwarden-backup-hourly-db.timer
systemctl enable --now vaultwarden-backup-daily-full.timer
systemctl enable --now vaultwarden-backup-monthly-full.timer
systemctl list-timers 'vaultwarden-backup-*'
```

Manual full backup:

```bash
systemctl start vaultwarden-backup@manual-full.service
```

## Small VPS Setup

On `ssh hetzner`:

```bash
install -d -m 0700 /srv/backups/vaultwarden/hourly-db
install -d -m 0700 /srv/backups/vaultwarden/daily-full
install -d -m 0700 /srv/backups/vaultwarden/monthly-full
install -d -m 0700 /etc/vaultwarden-backup
```

Replace generic shell access with a restricted backup user:

```bash
useradd --system --home /srv/backups/vaultwarden --shell /usr/sbin/nologin vwbackup
chown -R vwbackup:vwbackup /srv/backups/vaultwarden
```

Install AX41 upload key in `/home/vwbackup/.ssh/authorized_keys` with a forced command that only accepts `rsync --server` into `/srv/backups/vaultwarden`. Do not grant general shell access for backup upload.

## Monitoring

Primary: Healthchecks.io.

Create checks:

- `vaultwarden-backup-hourly-db`
  - Schedule: cron `17 * * * *`
  - Timezone: UTC
  - Grace: 30 minutes
- `vaultwarden-backup-daily-full`
  - Schedule: cron `43 3 * * *`
  - Timezone: UTC
  - Grace: 2 hours
- `vaultwarden-backup-monthly-full`
  - Schedule: cron `11 4 1 * *`
  - Timezone: UTC
  - Grace: 6 hours
- `vaultwarden-remote-b2-check`
  - Schedule: cron `29 5 * * *`
  - Timezone: UTC
  - Grace: 2 hours
- `vaultwarden-semantic-canary`
  - Schedule: cron `7 6 * * *`
  - Timezone: UTC
  - Grace: 2 hours
- `vaultwarden-restore-drill-quarterly`
  - Manual ping only after successful full drill.
  - Period: 100 days.

Alert targets:

- Federico email.
- Secondary mailbox not controlled by the same Gmail account.
- ntfy.sh topic if already used.
- Existing floom heartbeat reads `/var/lib/vaultwarden-backup/last-success.json` as a secondary local signal.

## Automated Remote Integrity Check

This check runs on the small VPS using a B2 read-only key scoped to the backup bucket.

Write `/usr/local/sbin/vaultwarden-backup-remote-check.sh` with mode `0750`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

source /etc/vaultwarden-backup/b2-readonly.env
HC_URL='https://hc-ping.com/REPLACE_REMOTE_CHECK_UUID'
WORK="$(mktemp -d /var/tmp/vw-remote-check.XXXXXX)"
cleanup() { rm -rf "$WORK"; }
fail() {
  rc=$?
  curl -fsS -m 10 --retry 3 "$HC_URL/fail" >/dev/null 2>&1 || true
  cleanup
  exit "$rc"
}
trap fail ERR
trap cleanup EXIT

curl -fsS -m 10 --retry 3 "$HC_URL/start" >/dev/null 2>&1 || true

KEY="$(aws s3api list-objects-v2 \
  --bucket "$B2_BUCKET" \
  --prefix 'd/' \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --query 'sort_by(Contents[?ends_with(Key, `.tar.zst.age`)], &LastModified)[-1].Key' \
  --output text)"

BASE="$(basename "$KEY")"
DIR="$(dirname "$KEY")"

aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL" "$WORK/$BASE" >/dev/null
aws s3api get-object --bucket "$B2_BUCKET" --key "$DIR/$BASE.sha256" --endpoint-url "$B2_ENDPOINT_URL" "$WORK/$BASE.sha256" >/dev/null
aws s3api get-object --bucket "$B2_BUCKET" --key "$DIR/$BASE.sig" --endpoint-url "$B2_ENDPOINT_URL" "$WORK/$BASE.sig" >/dev/null
aws s3api get-object-retention --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL" > "$WORK/retention.json"

(cd "$WORK" && sha256sum -c "$BASE.sha256")
ssh-keygen -Y verify \
  -f /etc/vaultwarden-backup/allowed_signers \
  -I vaultwarden-backup@ax41 \
  -n vaultwarden-backup \
  -s "$WORK/$BASE.sig" < "$WORK/$BASE"

jq -e '.Retention.Mode == "COMPLIANCE" and (.Retention.RetainUntilDate | length > 0)' "$WORK/retention.json" >/dev/null

curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
```

Cron on the small VPS:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

29 5 * * * root /usr/local/sbin/vaultwarden-backup-remote-check.sh >>/var/log/vaultwarden-backup-remote-check.log 2>&1
```

## Semantic Canary

Create a dedicated Vaultwarden account only for monitoring:

- Email: `vw-canary@vault.floom.dev` or equivalent.
- Unique random password stored only on the small VPS in `/etc/vaultwarden-backup/canary.env`.
- One item named exactly `VW BACKUP CANARY DO NOT DELETE`.
- One attachment named `vw-backup-canary.txt`.
- Attachment contents: a random 128-bit token printed in the recovery pack and stored in `/etc/vaultwarden-backup/canary.env` on the VPS.

Install Bitwarden CLI on the small VPS with a fixed major version:

```bash
npm install -g @bitwarden/cli@2026
bw --version
```

Create `/etc/vaultwarden-backup/canary.env` on the small VPS:

```bash
export BW_CLIENTID=''
export BW_CLIENTSECRET=''
export BW_PASSWORD='REPLACE_CANARY_PASSWORD'
export BW_SERVER='https://vault.floom.dev'
export BW_CANARY_ITEM='VW BACKUP CANARY DO NOT DELETE'
export BW_CANARY_ATTACHMENT='vw-backup-canary.txt'
export BW_CANARY_SHA256='REPLACE_EXPECTED_ATTACHMENT_SHA256'
export HC_URL='https://hc-ping.com/REPLACE_CANARY_UUID'
```

Write `/usr/local/sbin/vaultwarden-semantic-canary.sh`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
source /etc/vaultwarden-backup/canary.env

WORK="$(mktemp -d /var/tmp/vw-canary.XXXXXX)"
cleanup() { rm -rf "$WORK"; bw logout >/dev/null 2>&1 || true; }
fail() {
  rc=$?
  curl -fsS -m 10 --retry 3 "$HC_URL/fail" >/dev/null 2>&1 || true
  cleanup
  exit "$rc"
}
trap fail ERR
trap cleanup EXIT

curl -fsS -m 10 --retry 3 "$HC_URL/start" >/dev/null 2>&1 || true

bw config server "$BW_SERVER" >/dev/null
SESSION="$(bw login vw-canary@vault.floom.dev "$BW_PASSWORD" --raw)"
bw sync --session "$SESSION" >/dev/null
ITEM_ID="$(bw list items --search "$BW_CANARY_ITEM" --session "$SESSION" | jq -r '.[0].id')"
test "$ITEM_ID" != "null"
bw get attachment "$BW_CANARY_ATTACHMENT" --itemid "$ITEM_ID" --output "$WORK/$BW_CANARY_ATTACHMENT" --session "$SESSION" >/dev/null
echo "$BW_CANARY_SHA256  $WORK/$BW_CANARY_ATTACHMENT" | sha256sum -c -

curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
cleanup
```

Cron:

```cron
7 6 * * * root /usr/local/sbin/vaultwarden-semantic-canary.sh >>/var/log/vaultwarden-semantic-canary.log 2>&1
```

Limits:

- This detects service availability, login, sync, item retrieval, and attachment retrieval for the canary.
- This does not prove Federico's real vault rows are semantically correct.
- A root attacker on AX41 can preserve the canary while poisoning other items.

## Cold Restore Procedure

Inputs needed:

- Fresh Linux host with Docker and Docker Compose.
- Offline `age` identity or two valid Shamir shares.
- `allowed_signers` public signer line from the recovery pack.
- B2 read credentials, or access to the small VPS artifact directory.
- DNS access for `vault.floom.dev`.
- The recovery checklist with known high-value item titles and canary attachment hash.

Install tools on the fresh host:

```bash
apt-get update
apt-get install -y age zstd awscli sqlite3 curl ca-certificates jq rsync docker.io docker-compose-plugin
```

Download latest daily or monthly full artifact from B2:

```bash
export AWS_ACCESS_KEY_ID='B2_READ_KEY_ID'
export AWS_SECRET_ACCESS_KEY='B2_READ_APPLICATION_KEY'
export AWS_DEFAULT_REGION='eu-central-003'
export AWS_EC2_METADATA_DISABLED='true'
export B2_ENDPOINT_URL='https://s3.eu-central-003.backblazeb2.com'
export B2_BUCKET='bb-euc-7m4q2r-worm'

mkdir -p /root/vw-restore
cd /root/vw-restore

KEY="$(aws s3api list-objects-v2 \
  --bucket "$B2_BUCKET" \
  --prefix 'd/' \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --query 'sort_by(Contents[?ends_with(Key, `.tar.zst.age`)], &LastModified)[-1].Key' \
  --output text)"

BASE="$(basename "$KEY")"
DIR="$(dirname "$KEY")"
aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL" "$BASE"
aws s3api get-object --bucket "$B2_BUCKET" --key "$DIR/$BASE.sha256" --endpoint-url "$B2_ENDPOINT_URL" "$BASE.sha256"
aws s3api get-object --bucket "$B2_BUCKET" --key "$DIR/$BASE.sig" --endpoint-url "$B2_ENDPOINT_URL" "$BASE.sig"
aws s3api get-object-retention --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL" > object-retention.json
```

Verify provenance and integrity:

```bash
sha256sum -c "$BASE.sha256"

ssh-keygen -Y verify \
  -f ./allowed_signers \
  -I vaultwarden-backup@ax41 \
  -n vaultwarden-backup \
  -s "$BASE.sig" < "$BASE"

jq -e '.Retention.Mode == "COMPLIANCE"' object-retention.json
```

Decrypt and inspect:

```bash
mkdir -p /root/vw-restore/extracted
age -d -i ./vaultwarden-backup-primary-age-identity-2026Q2.txt "$BASE" \
  | zstd -d \
  | tar -x -C /root/vw-restore/extracted

cd /root/vw-restore/extracted
sha256sum -c MANIFEST.sha256
sqlite3 data/db.sqlite3 'PRAGMA integrity_check;'
sqlite3 data/db.sqlite3 'PRAGMA foreign_key_check;'
sqlite3 data/db.sqlite3 'SELECT COUNT(*) AS users FROM users; SELECT COUNT(*) AS ciphers FROM ciphers;'

find data/attachments -type f -printf '%P\t%s\t' -exec sha256sum {} \; 2>/dev/null \
  | awk -F '\t|  ' '{print $1 "\t" $2 "\t" $3}' | sort > /tmp/restored-attachments.tsv
diff -u ATTACHMENTS.tsv /tmp/restored-attachments.tsv
```

Restore files:

```bash
systemctl stop vaultwarden 2>/dev/null || true
docker stop vaultwarden 2>/dev/null || true

install -d -m 0700 /opt/vaultwarden/data
rsync -a --delete /root/vw-restore/extracted/data/ /opt/vaultwarden/data/
rsync -a /root/vw-restore/extracted/opt/vaultwarden/ /opt/vaultwarden/

rm -f /opt/vaultwarden/data/db.sqlite3-wal /opt/vaultwarden/data/db.sqlite3-shm
sqlite3 /opt/vaultwarden/data/db.sqlite3 'PRAGMA integrity_check;'
```

Start Vaultwarden:

```bash
cd /opt/vaultwarden
docker compose up -d
docker logs --tail=100 vaultwarden
```

Bring service back:

1. Restore or recreate nginx for `vault.floom.dev`.
2. Point DNS to the recovery host.
3. Obtain TLS certificate.
4. Open `https://vault.floom.dev`.
5. Log in with an existing real account.
6. Verify the canary account and canary attachment.
7. Verify the offline checklist of high-value real item titles and attachment names.
8. Verify one organization item if any exists.
9. Verify one send if sends exist.
10. Run a Bitwarden client sync from a clean client profile.

## Quarterly Full Drill

Cadence: first weekend of January, April, July, October.

Pass criteria:

- Uses a fresh host or VM.
- Downloads the selected artifact from B2, not from local AX41 files.
- Verifies Object Lock metadata.
- Verifies SHA-256 and OpenSSH signature.
- Uses the offline `age` identity or a live Shamir reconstruction.
- Restores from backed-up compose/env files.
- Starts the pinned Vaultwarden image digest or records an explicit deliberate upgrade test.
- Logs in with the canary account.
- Downloads `vw-backup-canary.txt` through Vaultwarden and matches the expected SHA-256.
- Logs in with Federico's real account.
- Verifies the offline checklist of high-value item titles and attachment names.
- Verifies SQLite `integrity_check`, `foreign_key_check`, DB counts, attachment manifest, and sends manifest.
- Destroys the drill host or securely deletes extracted plaintext after the drill.
- Pings the restore-drill Healthchecks URL only after all pass criteria succeed.

Failure examples:

- Artifact decrypts but attachment manifest diff fails: drill fails.
- Vaultwarden boots but canary attachment cannot be downloaded: drill fails.
- Can log in only by pulling `latest`: drill fails until the pinned-image restore path is fixed.
- Healthchecks URL is pinged before manual item verification: drill invalid.

## Vaultwarden Upgrade Procedure

Automatic Vaultwarden upgrades are disabled.

Before any upgrade:

```bash
systemctl start vaultwarden-backup@manual-full.service
journalctl -u vaultwarden-backup@manual-full.service -n 200 --no-pager
```

Record current image digest:

```bash
cd /opt/vaultwarden
docker compose images
docker inspect --format='{{index .RepoDigests 0}}' vaultwarden
```

After upgrade:

```bash
docker compose pull
docker compose up -d
docker logs --tail=200 vaultwarden
/usr/local/sbin/vaultwarden-semantic-canary.sh
systemctl start vaultwarden-backup@manual-full.service
```

If the upgrade changes the SQLite schema, keep both the pre-upgrade and post-upgrade manual-full artifacts. During disaster recovery, start with the image digest recorded in the selected artifact unless intentionally restoring into a newer version.

## Backblaze Account Audit

Monthly from an admin workstation:

```bash
aws s3api list-buckets --endpoint-url "$B2_ENDPOINT_URL"
aws s3api get-object-lock-configuration --bucket "$B2_BUCKET" --endpoint-url "$B2_ENDPOINT_URL"
aws s3api list-objects-v2 --bucket "$B2_BUCKET" --prefix h/ --max-items 5 --endpoint-url "$B2_ENDPOINT_URL"
aws s3api list-objects-v2 --bucket "$B2_BUCKET" --prefix d/ --max-items 5 --endpoint-url "$B2_ENDPOINT_URL"
aws s3api list-objects-v2 --bucket "$B2_BUCKET" --prefix m/ --max-items 5 --endpoint-url "$B2_ENDPOINT_URL"
```

Manual web-console checks:

- Account email is still the dedicated backup email.
- 2FA is enabled.
- Recovery codes are still stored in the paper recovery pack.
- No unknown buckets exist.
- No unknown application keys exist.
- Billing usage matches the storage model.
- Region displays EU Central.
- DPA status is recorded.

Compromise response:

- If Backblaze account compromise is suspected, create a new dedicated EU Central account, create a new Object Lock bucket, rotate B2 app keys, rotate object prefixes, and run `manual-full`.
- Existing locked objects in the compromised account remain useful if ciphertext keys are uncompromised, but metadata and billing integrity are no longer trusted.

## Subtle Attack Coverage

Backup-server compromise:

- VPS copies are encrypted and signed.
- B2 locked copies remain available if the VPS is wiped.

B2 compromise:

- Existing Compliance-mode objects cannot be shortened or deleted before retention expiry.
- B2 compromise still exposes metadata and can create billing abuse.
- Dedicated account, opaque names, EU region, restricted keys, and monthly account audit reduce but do not eliminate this risk.

AX41 root compromise:

- Root gets live database files, config, B2 write key, signing key, scripts, and Healthchecks URLs.
- Backups created during the compromise are untrusted unless external evidence proves otherwise.
- Daily canary and remote B2 checks bound some detection windows.
- Quarterly drills catch broad semantic failures.
- Targeted poisoned valid rows remain a residual risk.

Snapshot poisoning:

- SQLite `integrity_check` and `foreign_key_check` catch structural corruption.
- Attachment and sends manifests catch missing files in full artifacts.
- Canary checks and real-account drill checks catch selected semantic failures.
- No checksum can prove encrypted user cipher contents are the intended human secrets.

Time-bomb attack:

- Hourly DB history survives 430 days.
- Monthly full snapshots survive seven years.
- If corruption is discovered after 430 days and every monthly full is poisoned, the plan has no clean data source. The mitigation is manual real-account checking, semantic exports before upgrades, and prompt investigation of canary/count drift.

## Decisions Before Implementation

- Create or approve the dedicated Backblaze EU Central account.
- Approve the opaque B2 bucket name.
- Accept Compliance mode and the fact that mistaken long retention cannot be shortened normally.
- Complete the primary, escrow, and Shamir key ceremony before production.
- Select Shamir holders.
- Create Healthchecks checks and paste URLs into `backup.env`.
- Create the canary Vaultwarden account and canary attachment.
- Approve the attachment RPO tradeoff: normal attachment RPO under 24 hours, with `manual-full` after critical document uploads.
- Pin the Vaultwarden image tag and digest.
- Approve disabling signups and replacing the plaintext admin token with an Argon2 PHC hash.
- Put quarterly restore drills on the calendar.

## Evidence Sources

- Backblaze B2 pricing: https://www.backblaze.com/cloud-storage/pricing
- Backblaze B2 Object Lock: https://www.backblaze.com/docs/cloud-storage-object-lock
- Backblaze EU region and metadata note: https://www.backblaze.com/blog/announcing-our-first-european-data-center/
- Backblaze data regions: https://www.backblaze.com/docs/cloud-storage-data-regions
- Backblaze privacy/DPA pages: https://www.backblaze.com/company/policy/privacy and https://help.backblaze.com/hc/en-us/articles/360004146953-Data-Processing-Addendum
- European Commission EU-US Data Privacy Framework adequacy decision: https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/eu-us-data-transfers_en
- SQLite Online Backup API: https://www.sqlite.org/backup.html
- SQLite PRAGMA integrity/quick checks: https://www.sqlite.org/pragma.html
- age usage and multiple recipients: https://github.com/FiloSottile/age
