# Vaultwarden Backup Strategy

Status: design ready, not implemented.

Scope: Vaultwarden on AX41 at `/opt/vaultwarden`, SQLite data at `/opt/vaultwarden/data`, secondary copy on the small Hetzner VPS, immutable offsite copy outside Hetzner.

## Decision

Use self-contained encrypted backup artifacts, not a mutable backup repository as the source of truth.

Pipeline:

1. AX41 creates a consistent SQLite snapshot using `sqlite3 .backup`.
2. AX41 copies restore-critical Vaultwarden files and adjacent ops files into a staging directory.
3. AX41 creates `tar.zst`, encrypts it with `age` to an offline public recipient, signs the encrypted artifact with an AX41-only SSH signing key, and verifies the SQLite copy before upload.
4. AX41 sends the encrypted artifact to:
   - small Hetzner VPS for fast recovery and host-loss redundancy,
   - Backblaze B2 bucket with Object Lock in Compliance mode for true offsite immutable history.
5. Healthchecks.io monitors every backup run. A separate restore-drill check covers manual full decrypt restores.

This gives:

- AX41 death: restore from VPS or B2.
- Small VPS death: restore from B2.
- Accidental deletion/corruption: timestamped versions plus long retention.
- Ransomware on AX41: B2 Object Lock prevents deletion or overwrite before retention expiry.
- Backup-server compromise: attacker can delete VPS copies, but cannot decrypt them and cannot erase locked B2 objects.
- Hetzner account loss: B2 remains outside the Hetzner account.

## 3-2-1 Application

Copies:

1. Primary live data: `/opt/vaultwarden/data` on AX41.
2. Secondary copy: encrypted artifacts on the small Hetzner VPS.
3. True offsite copy: encrypted immutable artifacts in Backblaze B2.

Media/control planes:

- AX41 local disk.
- Small VPS disk in the same provider account.
- Backblaze B2 object storage in a separate provider account.

Offsite:

- The small Hetzner VPS is geographically secondary, but not a true offsite copy for account-level disaster because it shares Hetzner Cloud billing/control-plane risk.
- Backblaze B2 counts as the required offsite copy.
- Hetzner Storage Box does not count as true offsite for this threat model, even if it lives in another Hetzner product family.

## What To Back Up

Backup every run:

- `/opt/vaultwarden/data/db.sqlite3` via `.backup` only.
- `/opt/vaultwarden/data/rsa_key.pem`, `rsa_key.der`, `rsa_key.pub.der` if present.
- `/opt/vaultwarden/data/attachments/` if present.
- `/opt/vaultwarden/data/sends/` if present.
- `/opt/vaultwarden/data/config.json` if present.
- `/opt/vaultwarden/data/admin-token` because the current token is plaintext and restore-critical for admin access.
- `/opt/vaultwarden/docker-compose.yml`.
- `/opt/vaultwarden/.env` if present.
- `/opt/vaultwarden/migrate-secrets.py`.
- `/opt/vaultwarden/migration-log.json`.
- `/opt/vaultwarden/wrappers/`.

Do not back up as authoritative state:

- `db.sqlite3-wal` and `db.sqlite3-shm` from the live directory. The `.backup` output is a clean database snapshot. During restore, remove stale `-wal` and `-shm` files before starting Vaultwarden.
- `icon_cache/`; it is cache. Including it is harmless but unnecessary.

Immediate hardening adjacent to backup:

- Set `SIGNUPS_ALLOWED=false` before exposing `vault.floom.dev`.
- Replace the plaintext admin token with an Argon2-hashed admin token.
- Avoid `vaultwarden/server:latest-alpine` after initial stabilization; pin a known image tag for reproducible restores.

## Encryption And Signing

Primary encryption: `age` public-key encryption.

Reason:

- The backup server only needs a public recipient.
- No backup decryption passphrase lives in Vaultwarden.
- No symmetric restic/borg password has to sit on AX41 for unattended encryption.
- Restore requires the offline age identity, which is the intended recovery boundary.

Signing: OpenSSH detached signatures over the encrypted artifact.

Reason:

- The small VPS cannot forge replacement artifacts.
- B2 cannot forge replacement artifacts.
- Restore verifies both SHA-256 and the AX41 signing key before decrypting.
- AX41 root compromise can still sign malicious backups; retention and restore drills mitigate that class.

Not selected as the primary path:

- `gpg` with passphrase: too much agent/keyring complexity for a cron job and creates passphrase handling problems.
- `rclone crypt`: good transport encryption, weaker as a recovery artifact format.
- restic native: excellent for larger mutable datasets, but repository locks, forget/prune, and Object Lock interact badly. A WORM bucket can lock restic lock files and prevent cleanup.
- borg native: strong for SSH append-only targets, but not needed for a 320 KB dataset and still needs key/passphrase handling unless backing up pre-encrypted artifacts.
- Vaultwarden admin export endpoint: useful as a human-readable/export layer, but not a complete server restore. It does not replace database, RSA keys, sends, attachments, and config backups.

## Recursive Passphrase Decision

Primary recommendation: one offline `age` identity printed on paper and stored in Federico's physical safe or safe deposit box. Store only the public recipient on AX41.

Fallback: split the same `age` identity with Shamir 2-of-3 and distribute the shares to Federico, parents, and Falco or a lawyer. Use this only after the paper copy exists, because recovery from Shamir has more operational ceremony.

Do not store the backup private key, age identity, or passphrase in Vaultwarden. That makes the backup unrecoverable exactly when Vaultwarden is lost.

Commands for the offline key ceremony:

```bash
age-keygen -o vaultwarden-backup-age-identity.txt
age-keygen -y vaultwarden-backup-age-identity.txt > vaultwarden-backup-age-recipient.txt
```

Print `vaultwarden-backup-age-identity.txt`. Put `vaultwarden-backup-age-recipient.txt` on AX41 at `/etc/vaultwarden-backup/age-recipient`.

## Storage Target Decision

Primary offsite target: Backblaze B2 with Object Lock enabled.

Cost at current dataset size is effectively zero: B2 lists $6.95/TB/month, first 10 GB free, free transactions for normal B2 classes, and Object Lock has no extra feature fee. At 1 MB per artifact, hourly backups for 400 days plus daily backups for 7 years stay below the free 10 GB storage allowance. At 100 MB per artifact, the same retention is roughly 1.2 TB, about $8.45/month before currency/VAT effects.

Comparisons:

- Backblaze B2: best fit here. Separate provider, S3-compatible API, Object Lock Compliance mode, cheap, no minimum object duration.
- Cloudflare R2: strong pricing and free egress; R2 has bucket lock API support, but B2 Object Lock has clearer backup/ransomware documentation and mature S3 object-lock workflows.
- Hetzner Storage Box: good secondary target, not true offsite for this threat model because it shares Hetzner account/provider risk.
- AWS S3 Deep Archive: excellent long-term archive, but restore friction, object minimums, retrieval charges, and API complexity add little value for a tiny hot recovery secret.
- rsync.net: strong alternative, especially Borg append-only and ZFS snapshots. Cost starts at 100 GB for $18/year for Borg accounts. Use it as the fallback offsite if Backblaze is rejected.

## Schedule

Use UTC for all cron entries.

- Hourly full encrypted artifact at minute 17. RPO is under 1 hour.
- Daily full encrypted artifact at 03:43 UTC. Same content class, longer B2 retention.
- Monthly automated remote integrity check from the small VPS: download latest B2 ciphertext, verify SHA-256, verify SSH signature, verify Object Lock metadata. It does not decrypt real data.
- Quarterly manual full restore drill with Federico present and the offline age identity available.

Reason for no unattended real-data decrypt drill:

- A full automated restore drill needs the age private key online.
- Keeping the private key online defeats the recursive-passphrase solution.
- The secure design runs automated non-decrypt integrity checks and scheduled manual decrypt restores.

## Retention

B2 immutable:

- Hourly prefix: retain 430 days with Object Lock Compliance.
- Daily prefix: retain 2555 days, about 7 years, with Object Lock Compliance.

Small VPS:

- Hourly: 30 days.
- Daily: 180 days.
- Monthly: 24 months if a monthly copy job is added later.

Detection-window rationale:

- Corruption detected days or weeks later is covered by 430 days of hourly history.
- Time-bomb attacks are harder because daily snapshots survive 7 years.
- B2 lifecycle cleanup can delete expired objects after retention; deletion before retention is blocked by Object Lock.

## AX41 Setup Commands

Install tools:

```bash
apt-get update
apt-get install -y sqlite3 age zstd awscli rsync curl ca-certificates
```

Create directories:

```bash
install -d -m 0700 /etc/vaultwarden-backup
install -d -m 0700 /var/backups/vaultwarden/hourly
install -d -m 0700 /var/backups/vaultwarden/daily
install -d -m 0700 /var/lib/vaultwarden-backup
```

Install the public age recipient:

```bash
install -m 0444 vaultwarden-backup-age-recipient.txt /etc/vaultwarden-backup/age-recipient
```

Create the signing key on AX41:

```bash
ssh-keygen -t ed25519 -N '' -C vaultwarden-backup@ax41 -f /etc/vaultwarden-backup/signing_key
chmod 0400 /etc/vaultwarden-backup/signing_key
ssh-keygen -y -f /etc/vaultwarden-backup/signing_key > /etc/vaultwarden-backup/signing_key.pub
chmod 0444 /etc/vaultwarden-backup/signing_key.pub
```

Create `/etc/vaultwarden-backup/allowed_signers` and store a printed copy with the age identity:

```bash
printf 'vaultwarden-backup@ax41 %s\n' "$(cat /etc/vaultwarden-backup/signing_key.pub)" > /etc/vaultwarden-backup/allowed_signers
chmod 0444 /etc/vaultwarden-backup/allowed_signers
```

Create B2 bucket with Object Lock enabled:

```bash
export AWS_ACCESS_KEY_ID='<B2 key id with bucket create/admin permission>'
export AWS_SECRET_ACCESS_KEY='<B2 application key>'
export AWS_DEFAULT_REGION='us-west-002'
export B2_ENDPOINT_URL='https://s3.us-west-002.backblazeb2.com'
export B2_BUCKET='fede-vaultwarden-worm'

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

Create a restricted B2 application key for the cron job:

- Bucket: `fede-vaultwarden-worm`.
- Capabilities: list bucket, list files, read files, write files, write file retentions.
- No delete capability.

Create `/etc/vaultwarden-backup/backup.env`:

```bash
cat >/etc/vaultwarden-backup/backup.env <<'EOF'
export AWS_ACCESS_KEY_ID='REPLACE_WITH_RESTRICTED_B2_KEY_ID'
export AWS_SECRET_ACCESS_KEY='REPLACE_WITH_RESTRICTED_B2_APPLICATION_KEY'
export AWS_DEFAULT_REGION='us-west-002'
export AWS_EC2_METADATA_DISABLED='true'

B2_ENDPOINT_URL='https://s3.us-west-002.backblazeb2.com'
B2_BUCKET='fede-vaultwarden-worm'

VW_DATA='/opt/vaultwarden/data'
VW_ROOT='/opt/vaultwarden'
AGE_RECIPIENT_FILE='/etc/vaultwarden-backup/age-recipient'
SIGNING_KEY='/etc/vaultwarden-backup/signing_key'
LOCAL_BACKUP_ROOT='/var/backups/vaultwarden'
REMOTE_VPS='hetzner'
REMOTE_VPS_DIR='/srv/backups/vaultwarden'

HEALTHCHECKS_HOURLY_URL='https://hc-ping.com/REPLACE_HOURLY_UUID'
HEALTHCHECKS_DAILY_URL='https://hc-ping.com/REPLACE_DAILY_UUID'
EOF
chmod 0600 /etc/vaultwarden-backup/backup.env
```

## Backup Script

Write `/usr/local/sbin/vaultwarden-backup.sh` with mode `0750`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

MODE="${1:-hourly}"
case "$MODE" in
  hourly|daily) ;;
  *) echo "usage: $0 hourly|daily" >&2; exit 64 ;;
esac

source /etc/vaultwarden-backup/backup.env

HC_URL="$HEALTHCHECKS_HOURLY_URL"
RETENTION_DAYS=430
if [ "$MODE" = "daily" ]; then
  HC_URL="$HEALTHCHECKS_DAILY_URL"
  RETENTION_DAYS=2555
fi

WORK="$(mktemp -d /var/tmp/vw-backup.XXXXXX)"
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

for bin in sqlite3 age zstd tar sha256sum aws ssh-keygen rsync curl find; do
  command -v "$bin" >/dev/null
done

TS="$(date -u +%Y%m%dT%H%M%SZ)"
EPOCH="$(date -u +%s)"
HOST="$(hostname -f 2>/dev/null || hostname)"
STAGE="$WORK/stage"
OUTDIR="$LOCAL_BACKUP_ROOT/$MODE"
BASE="vaultwarden-${HOST}-${MODE}-${TS}"
ARTIFACT="$OUTDIR/${BASE}.tar.zst.age"

install -d -m 0700 "$STAGE/data" "$STAGE/opt/vaultwarden" "$OUTDIR"

sqlite3 "$VW_DATA/db.sqlite3" ".timeout 5000" ".backup '$STAGE/data/db.sqlite3'"
test "$(sqlite3 "$STAGE/data/db.sqlite3" 'PRAGMA quick_check;')" = "ok"
test "$(sqlite3 "$STAGE/data/db.sqlite3" 'PRAGMA integrity_check;')" = "ok"

for f in rsa_key.pem rsa_key.der rsa_key.pub.der config.json admin-token; do
  [ -f "$VW_DATA/$f" ] && cp -a "$VW_DATA/$f" "$STAGE/data/$f"
done

for d in attachments sends; do
  [ -d "$VW_DATA/$d" ] && rsync -a "$VW_DATA/$d/" "$STAGE/data/$d/"
done

for p in docker-compose.yml .env migrate-secrets.py migration-log.json; do
  [ -f "$VW_ROOT/$p" ] && cp -a "$VW_ROOT/$p" "$STAGE/opt/vaultwarden/$p"
done

[ -d "$VW_ROOT/wrappers" ] && rsync -a "$VW_ROOT/wrappers/" "$STAGE/opt/vaultwarden/wrappers/"

USER_COUNT="$(sqlite3 "$STAGE/data/db.sqlite3" 'SELECT COUNT(*) FROM users;' 2>/dev/null || echo unknown)"
CIPHER_COUNT="$(sqlite3 "$STAGE/data/db.sqlite3" 'SELECT COUNT(*) FROM ciphers;' 2>/dev/null || echo unknown)"
ATTACHMENT_BYTES="$(du -sb "$STAGE/data/attachments" 2>/dev/null | awk '{print $1}' || echo 0)"

cat >"$STAGE/MANIFEST.json" <<EOF
{
  "created_utc": "$TS",
  "source_host": "$HOST",
  "mode": "$MODE",
  "vaultwarden_root": "$VW_ROOT",
  "vaultwarden_data": "$VW_DATA",
  "sqlite_quick_check": "ok",
  "sqlite_integrity_check": "ok",
  "user_count": "$USER_COUNT",
  "cipher_count": "$CIPHER_COUNT",
  "attachment_bytes": "$ATTACHMENT_BYTES"
}
EOF

cat >"$STAGE/RESTORE-NOTES.txt" <<EOF
Restore notes:
1. Stop Vaultwarden before replacing files.
2. Restore data/db.sqlite3 as /opt/vaultwarden/data/db.sqlite3.
3. Delete stale /opt/vaultwarden/data/db.sqlite3-wal and db.sqlite3-shm before start.
4. Restore rsa_key.* with the database so existing clients can keep using signed sessions.
5. Point vault.floom.dev to the recovered host before normal use.
EOF

(cd "$STAGE" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256)

tar --sort=name --mtime="@$EPOCH" --owner=0 --group=0 --numeric-owner -C "$STAGE" -cf - . \
  | zstd -T1 -10 \
  | age -r "$(cat "$AGE_RECIPIENT_FILE")" -o "$ARTIFACT"

(cd "$OUTDIR" && sha256sum "$(basename "$ARTIFACT")" > "$(basename "$ARTIFACT").sha256")
ssh-keygen -Y sign -f "$SIGNING_KEY" -n vaultwarden-backup "$ARTIFACT" >/dev/null

RETAIN_UNTIL="$(date -u -d "+${RETENTION_DAYS} days" '+%Y-%m-%dT%H:%M:%SZ')"
for f in "$ARTIFACT" "$ARTIFACT.sha256" "$ARTIFACT.sig"; do
  key="vaultwarden/${MODE}/$(basename "$f")"
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

find "$LOCAL_BACKUP_ROOT/hourly" -type f -mtime +30 -delete 2>/dev/null || true
find "$LOCAL_BACKUP_ROOT/daily" -type f -mtime +180 -delete 2>/dev/null || true

cat > /var/lib/vaultwarden-backup/last-success.json <<EOF
{
  "created_utc": "$TS",
  "mode": "$MODE",
  "artifact": "$(basename "$ARTIFACT")",
  "b2_retention_until": "$RETAIN_UNTIL",
  "user_count": "$USER_COUNT",
  "cipher_count": "$CIPHER_COUNT",
  "attachment_bytes": "$ATTACHMENT_BYTES"
}
EOF

curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
```

Install it:

```bash
install -m 0750 vaultwarden-backup.sh /usr/local/sbin/vaultwarden-backup.sh
```

## Small VPS Setup

On `ssh hetzner`:

```bash
install -d -m 0700 /srv/backups/vaultwarden/hourly
install -d -m 0700 /srv/backups/vaultwarden/daily
```

The current AX41 to Hetzner SSH key path is enough for initial implementation. For a tighter second pass, replace shell access with a restricted backup user and forced upload command.

## Cron Entries

Create `/etc/cron.d/vaultwarden-backup` on AX41:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

17 * * * * root /usr/local/sbin/vaultwarden-backup.sh hourly >>/var/log/vaultwarden-backup.log 2>&1
43 3 * * * root /usr/local/sbin/vaultwarden-backup.sh daily >>/var/log/vaultwarden-backup.log 2>&1
```

Timing rationale:

- Minute 17 avoids the top-of-hour cron herd.
- Daily run at 03:43 UTC is quiet for Europe and US.
- Hourly artifacts give low RPO. Daily artifacts give long-term retention without relying on hourly lifecycle.

## Monitoring

Primary: Healthchecks.io.

Create checks:

- `vaultwarden-backup-hourly`
  - Schedule: cron `17 * * * *`
  - Timezone: UTC
  - Grace: 30 minutes
  - Ping URL goes into `HEALTHCHECKS_HOURLY_URL`
- `vaultwarden-backup-daily`
  - Schedule: cron `43 3 * * *`
  - Timezone: UTC
  - Grace: 2 hours
  - Ping URL goes into `HEALTHCHECKS_DAILY_URL`
- `vaultwarden-restore-drill-quarterly`
  - Manual ping after each successful full restore drill.
  - Period: 100 days.
  - This creates an alert when the manual drill is overdue.

Alert targets:

- Federico email.
- ntfy.sh topic if already used.
- Existing floom heartbeat can read `/var/lib/vaultwarden-backup/last-success.json` as a secondary local signal.

## Automated Remote Integrity Check

Write `/usr/local/sbin/vaultwarden-backup-remote-check.sh` on the small VPS with mode `0750`:

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
  --prefix 'vaultwarden/daily/' \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --query 'sort_by(Contents[?ends_with(Key, `.tar.zst.age`)], &LastModified)[-1].Key' \
  --output text)"

BASE="$(basename "$KEY")"
aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL" "$WORK/$BASE" >/dev/null
aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY.sha256" --endpoint-url "$B2_ENDPOINT_URL" "$WORK/$BASE.sha256" >/dev/null
aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY.sig" --endpoint-url "$B2_ENDPOINT_URL" "$WORK/$BASE.sig" >/dev/null
aws s3api get-object-retention --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL" >/dev/null

(cd "$WORK" && sha256sum -c "$BASE.sha256")
ssh-keygen -Y verify \
  -f /etc/vaultwarden-backup/allowed_signers \
  -I vaultwarden-backup@ax41 \
  -n vaultwarden-backup \
  -s "$WORK/$BASE.sig" < "$WORK/$BASE"

curl -fsS -m 10 --retry 3 "$HC_URL" >/dev/null 2>&1 || true
```

Cron on the small VPS:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

29 5 1 * * root /usr/local/sbin/vaultwarden-backup-remote-check.sh >>/var/log/vaultwarden-backup-remote-check.log 2>&1
```

## Cold Restore Procedure

Inputs needed:

- Fresh Linux host with Docker and Docker Compose.
- Offline `vaultwarden-backup-age-identity.txt`.
- `/etc/vaultwarden-backup/allowed_signers` public signer line from the paper recovery pack or repo.
- B2 read credentials, or access to the small VPS artifact directory.
- DNS access for `vault.floom.dev`.

Install tools on the fresh host:

```bash
apt-get update
apt-get install -y age zstd awscli sqlite3 curl ca-certificates
```

Download latest daily artifact from B2:

```bash
export AWS_ACCESS_KEY_ID='B2_READ_KEY_ID'
export AWS_SECRET_ACCESS_KEY='B2_READ_APPLICATION_KEY'
export AWS_DEFAULT_REGION='us-west-002'
export AWS_EC2_METADATA_DISABLED='true'
export B2_ENDPOINT_URL='https://s3.us-west-002.backblazeb2.com'
export B2_BUCKET='fede-vaultwarden-worm'

mkdir -p /root/vw-restore
cd /root/vw-restore

KEY="$(aws s3api list-objects-v2 \
  --bucket "$B2_BUCKET" \
  --prefix 'vaultwarden/daily/' \
  --endpoint-url "$B2_ENDPOINT_URL" \
  --query 'sort_by(Contents[?ends_with(Key, `.tar.zst.age`)], &LastModified)[-1].Key' \
  --output text)"

BASE="$(basename "$KEY")"
aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL" "$BASE"
aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY.sha256" --endpoint-url "$B2_ENDPOINT_URL" "$BASE.sha256"
aws s3api get-object --bucket "$B2_BUCKET" --key "$KEY.sig" --endpoint-url "$B2_ENDPOINT_URL" "$BASE.sig"
aws s3api get-object-retention --bucket "$B2_BUCKET" --key "$KEY" --endpoint-url "$B2_ENDPOINT_URL"
```

Verify provenance and integrity:

```bash
sha256sum -c "$BASE.sha256"

ssh-keygen -Y verify \
  -f ./allowed_signers \
  -I vaultwarden-backup@ax41 \
  -n vaultwarden-backup \
  -s "$BASE.sig" < "$BASE"
```

Decrypt and inspect:

```bash
mkdir -p /root/vw-restore/extracted
age -d -i ./vaultwarden-backup-age-identity.txt "$BASE" | zstd -d | tar -x -C /root/vw-restore/extracted

cd /root/vw-restore/extracted
sha256sum -c MANIFEST.sha256
sqlite3 data/db.sqlite3 'PRAGMA integrity_check;'
sqlite3 data/db.sqlite3 'SELECT COUNT(*) AS users FROM users; SELECT COUNT(*) AS ciphers FROM ciphers;'
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
docker compose pull
docker compose up -d
docker logs --tail=100 vaultwarden
```

Bring service back:

1. Restore or recreate nginx for `vault.floom.dev`.
2. Point DNS to the recovery host.
3. Obtain TLS certificate.
4. Open `https://vault.floom.dev`.
5. Log in with an existing account.
6. Verify at least one known item, one organization item if any, sends if any, and attachment download if any.
7. Existing clients can remain authenticated if `rsa_key.pem` and domain are restored. If clients prompt again, log in normally with the master password and 2FA.

## Quarterly Full Drill

Cadence: first weekend of January, April, July, October.

Drill rules:

- Use a temporary host or an isolated local Docker project.
- Do not expose the drill instance publicly.
- Use the offline age identity.
- Verify signature before decrypt.
- Start Vaultwarden on `127.0.0.1:18222`.
- Log in with a real account.
- Confirm counts and spot-check items.
- Destroy the drill host or securely delete extracted plaintext after the drill.
- Ping the Healthchecks restore-drill URL only after a successful login and spot-check.

Example isolated compose override for a drill:

```bash
cd /opt/vaultwarden
docker compose up -d
ssh -L 18222:127.0.0.1:8222 recovery-host
```

Then visit `http://127.0.0.1:18222` through the tunnel.

## Subtle Attack Coverage

Backup-server compromise:

- VPS copies are encrypted and signed.
- B2 locked copies remain available even if the VPS is wiped.

Restoration social engineering:

- Restore only artifacts with a valid SHA-256 file and AX41 signing signature.
- Confirm B2 Object Lock metadata on the selected object.
- Prefer daily B2 prefix over random files handed over by a third party.

Snapshot poisoning:

- Every backup runs SQLite `quick_check` and `integrity_check` on the copied DB.
- Retention keeps old versions beyond normal detection windows.
- Quarterly restore drills catch semantic breakage that hashes cannot catch.

Time-bomb attack:

- Daily snapshots retain for 7 years.
- Quarterly manual drills detect drift while clean versions still exist.
- A future improvement is weekly Bitwarden CLI encrypted export as an additional semantic canary.

Key leakage via swap or coredump:

- AX41 only holds public age recipient, not the private decrypt key.
- B2 keys live in `0600` root-only env file.
- Disable coredumps for the backup script via systemd if converting cron to a timer later.
- Avoid putting secrets in command-line arguments; use env files and root-only files.

## Decisions Before Implementation

- Backblaze account: create or reuse one outside Hetzner.
- B2 region: pick `us-west-002` or EU region if available in the account and desired.
- B2 bucket name: default `fede-vaultwarden-worm`.
- Object Lock mode: accept Compliance mode and the fact that mistaken long retention cannot be shortened normally.
- Age recovery storage: physical safe or safe deposit box for the printed identity.
- Shamir fallback: decide trusted holders if using 2-of-3.
- Healthchecks.io account: create checks and paste URLs into `backup.env`.
- Alert channel: email, ntfy, or both.
- Restore drill calendar: approve quarterly manual drill cadence.
- Admin hardening: approve disabling signups and replacing plaintext admin token with Argon2 hash.
- Image pinning: choose the Vaultwarden image tag to pin after the first successful backup and restore drill.

## Evidence Sources

- Vaultwarden documents SQLite `.backup`, attachments/sends, RSA token signing keys, and stale WAL restore caveat.
- SQLite documents the Online Backup API as creating a snapshot while the source database remains usable.
- Backblaze documents Object Lock immutability, Compliance/Governance retention behavior, S3 API examples, and no extra Object Lock fee.
- Backblaze pricing page lists B2 at $6.95/TB/month, first 10 GB free, free normal transactions, and free egress up to 3x average monthly storage.
- Healthchecks.io documents dead-man-switch monitoring for cron jobs.
