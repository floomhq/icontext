# Key management architecture — Codex consultation

> Source: `codex exec` (codex-cli 0.128.0, frontier model, reasoning_effort=high)
> Date: 2026-05-05
> Session ID: `019df6f4-9ae6-73d0-a19d-1b02cf930196`
> Tokens used: 30,907

---

## TLDR

Use **option A: 1Password as the canonical recovery store** for the exported `git-crypt` repo key, protected by a strong account password, the 1Password Secret Key, hardware security keys for account auth, and a documented restore drill.

Do **not** migrate just to fix this. Your problem is key survivability, not file encryption mechanics. `git-crypt` is adequate if the key is backed up correctly and only trusted machines can write plaintext to encrypted paths.

For AX41: either give it `git-crypt` and accept "server compromise = vault compromise," or make AX41 structurally unable to write vault data. Given your data sensitivity and the recent leak, the recommendation is: **AX41 does not get the key by default, has no GitHub write credential for this repo, and uses sparse checkout excluding `vault/`.**

---

## Ranking

1. **A. git-crypt key in 1Password / Bitwarden** — Best solo-operator balance. Zero-knowledge cloud storage, survives machine loss, no per-commit friction, usable recovery.
2. **D. Passphrase-encrypted key in same private GitHub repo** — Strong as a secondary break-glass backup if the passphrase has high entropy. Weak as primary because GitHub compromise gives attackers offline brute-force material next to the encrypted data.
3. **E. Migrate to age** — Good crypto model, especially per-recipient identities, but it adds migration and workflow risk without solving backup by itself.
4. **C. YubiKey / hardware token** — Excellent for protecting accounts and auth, awkward as sole data-key custody. Needs duplicate tokens and a backup story anyway.
5. **B. iCloud Keychain** — Decent Apple-only emergency storage, weaker cross-platform fit, weaker operational audit, broader Apple-account recovery surface.
6. **F. Mac only** — Fails the core requirement. One hardware loss equals permanent vault loss.

---

## Top recommendation deep dive

Use the existing `git-crypt` setup and export the symmetric repo key once. Store that exported key as a secure file attachment in **1Password**, not loose in iCloud Drive, not in shell history, not in the repo unencrypted.

Prefer **1Password over Bitwarden** for this specific use case because 1Password adds a high-entropy **Secret Key** to the account password. If 1Password's cloud vault database is stolen, the attacker needs both the account password and the Secret Key before offline decryption attempts become realistic. Bitwarden can be strong with Argon2id and a high-entropy master password, but its default security model depends more heavily on the master password/KDF.

### Why it beats the others

A solves the exact failure mode: Mac dies, GitHub still has ciphertext, 1Password has the decryption key, Federico restores on a new trusted machine.

It avoids per-commit friction because `git-crypt` still handles encryption transparently after unlock.

It is more usable than YubiKey-only custody. Hardware tokens are great for protecting the password manager login, but bad as the only place where a long-lived data recovery secret exists. Tokens get lost, PIN-locked, damaged, and duplicated hardware-token setups become their own ceremony.

It is cleaner than iCloud Keychain because it works across Mac, Linux, browser, and CLI workflows, has better secret-item ergonomics, and avoids tying vault recovery entirely to Apple ID recovery flows.

It is safer than storing the encrypted key in the same repo as the only backup because a GitHub compromise does not automatically hand attackers a ciphertext specifically designed for offline password guessing.

### Failure modes

| Failure | Impact | Recovery |
|---|---|---|
| Mac dies | No vault loss | Clone repo on new trusted machine, retrieve key from 1Password, run `git-crypt unlock` |
| AX41 dies | No vault loss | Rebuild from GitHub. If AX41 never had the key, no cryptographic incident |
| GitHub compromised | Attacker gets encrypted blobs, filenames, paths, file sizes, commit timing, history | Cannot decrypt without the `git-crypt` key. Any prior plaintext leak in Git history remains exposed |
| 1Password cloud breached | Attacker gets encrypted vault data | Secret Key + account password protect against server-side vault theft |
| 1Password account taken over | If attacker gets into a decrypted client session, key is exposed | Hardware security keys, strong account password, recovery code custody, review trusted devices |
| Hardware token lost (used only for 1Password MFA) | Recover with second registered token or recovery code | If used as sole decryption key, loss can become permanent data loss |
| `git-crypt` key leaked once | Full historical vault compromise. Old encrypted Git blobs become decryptable forever | Rotation requires a new key and, for real containment, a new rewritten or fresh repository boundary |

---

## AX41 question

AX41 has two valid modes. Mixing them caused the recent leak.

### Mode 1: No plaintext authority on AX41 (recommended default)

Controls:
- AX41 has no `git-crypt` key.
- AX41 has no GitHub write credential for the vault repo.
- AX41 uses sparse checkout excluding `vault/`.
- Local hooks block accidental commits under `vault/`, but hooks are guardrails, not security boundaries.
- Main branch protection blocks merges unless CI passes a leak check.

The real security boundary is **no write credential**. GitHub does not give normal private repos path-level write permissions, so "AX41 can write non-vault files but cannot push `vault/` leaks" is not enforceable purely with GitHub permissions. For that, split repos or route AX41 changes through a trusted machine.

### Mode 2: AX41 can edit plaintext

Then AX41 needs `git-crypt`, the exported key, and the repo unlocked. This means server compromise equals vault compromise. Use this only if AX41 genuinely needs plaintext access.

Safe provisioning pattern:

```bash
cd /path/to/fede-vault
git-crypt unlock /path/to/fede-vault.git-crypt.key
git-crypt status -e
rm -f /path/to/fede-vault.git-crypt.key
```

Then after work:

```bash
cd /path/to/fede-vault
git status --short
git-crypt lock
```

Even after deleting the temporary key file, the server had plaintext and may have backups, shell logs, editor swap files, indexing, snapshots, or agent reads. Treat unlock on AX41 as a deliberate trust decision.

---

## A vs B comparison (1Password / Bitwarden vs iCloud Keychain)

Both are client-side decrypted cloud sync systems, but they differ operationally.

### 1Password is cleaner because

- Secret storage is the product's core job.
- 1Password Secret Key materially improves protection against cloud-vault database theft.
- Cross-platform restore is normal, including Linux.
- Item attachments, emergency kits, vault sharing, device review, and account security reports fit this job.
- It separates vault recovery from Apple ID recovery.

### iCloud Keychain is convenient because

- It is built into Apple devices.
- Sync is low-friction on Mac/iPhone.
- It has strong platform security when the Apple account and devices are healthy.

### iCloud is less clean here because

- AX41/Linux recovery is awkward.
- Auditability is limited.
- The recovery surface is Apple ID, trusted devices, device passcodes, and Apple account recovery.
- It encourages Apple-only thinking for a vault used across 2-3 machines.

For a solo operator, A is better if the goal is durable operational recovery. B is acceptable as an extra copy, not the canonical key-management architecture.

---

## Subtle attacks Codex flagged

- `git-crypt` does not hide filenames, paths, file sizes, or commit timing.
- A malicious or over-permissioned AI agent on an unlocked machine can read plaintext like any local process.
- Browser extensions can steal password-manager page content or downloaded key files.
- Clipboard managers can retain copied passphrases or keys.
- Shell history can capture paths, passphrases, or recovery commands.
- Git hooks are bypassable.
- CI leak checks happen after push; a pushed plaintext secret already reached GitHub.
- Server snapshots and backups can retain plaintext after an AX41 unlock.
- macOS Spotlight, editor swap files, Time Machine, iCloud Desktop/Documents, and backup tools can copy plaintext working trees.
- Supply-chain compromise of `git-crypt`, package managers, shell plugins, or repo scripts can steal the key at unlock time.
- Password-manager recovery flows can be socially engineered.
- GitHub OAuth apps and deploy keys often outlive the mental model of who has repo access.
- If the raw `git-crypt` key leaks once, historical encrypted blobs are decryptable forever.

---

## Implementation plan

### 1. On the trusted Mac, export the key

```bash
cd /path/to/fede-vault
umask 077
git-crypt status -e
git-crypt export-key "$HOME/fede-vault.git-crypt.key"
shasum -a 256 "$HOME/fede-vault.git-crypt.key"
```

### 2. Create a 1Password secure note named

```text
fede-vault git-crypt recovery key
```

Attach:

```text
$HOME/fede-vault.git-crypt.key
```

Record these fields in the note:

```text
Repo: git@github.com:OWNER/REPO.git
Key fingerprint: output of shasum -a 256
Created: 2026-05-05
Restore command: git-crypt unlock /path/to/fede-vault.git-crypt.key
```

### 3. Test recovery in a fresh clone

```bash
tmpdir="$(mktemp -d)"
git clone git@github.com:OWNER/REPO.git "$tmpdir"
cd "$tmpdir"
git-crypt unlock /path/to/restored/fede-vault.git-crypt.key
git-crypt status -e
git status --short
```

### 4. Remove the loose exported key after the restore test

```bash
rm -f "$HOME/fede-vault.git-crypt.key"
```

### 5. For AX41 no-plaintext mode

```bash
cd /path/to/fede-vault
git sparse-checkout init --no-cone
printf '/*\n!/vault/\n' > .git/info/sparse-checkout
git read-tree -mu HEAD
```

### 6. Add a local tripwire

```bash
cat > .git/hooks/pre-commit <<'EOF'
#!/bin/sh
if git diff --cached --name-only --diff-filter=ACMR | grep -q '^vault/'; then
  echo "AX41 is not allowed to commit vault/ changes" >&2
  exit 1
fi
EOF
chmod +x .git/hooks/pre-commit
```

### 7. Remove AX41's write path to GitHub for this repo

Use a read-only deploy key or no repo credential. That is the control that turns "avoid plaintext leaks" into an enforceable boundary.
