# Key management — recommendation

## TLDR

Keep `git-crypt`. Export the symmetric key, store it as a secure file attachment in **1Password** under a note named `fede-vault git-crypt recovery key`. Make AX41 structurally unable to write to `vault/` (no key, no write credential, sparse checkout excluding `vault/`, plus a pre-commit tripwire).

## Why this beats the alternatives

- **Survives single-machine loss without per-commit friction.** Mac dies → clone repo, retrieve key from 1Password, `git-crypt unlock`. AX41 dies → no cryptographic incident because the key never lived there.
- **Better cloud-breach posture than iCloud Keychain.** 1Password's Secret Key adds a second high-entropy factor on top of the master password, so a stolen 1Password vault database alone is not enough for offline attack. iCloud Keychain ties recovery to Apple ID flows that are out of scope for a Linux/cross-platform vault.
- **No migration risk.** Migrating to age (option E) does not solve the backup question by itself, just changes the encryption tool. The actual problem is key custody, not encryption mechanics.

## What Federico needs to do

1. On Mac: export the `git-crypt` key locally to `$HOME/fede-vault.git-crypt.key` (one command).
2. Create a 1Password secure note titled `fede-vault git-crypt recovery key`. Attach the exported key file. Record: repo URL, key SHA-256 fingerprint, created date, and restore command.
3. Confirm 1Password account hardening: Secret Key on file, hardware security key (YubiKey) registered for account auth, recovery code stored offline, trusted devices reviewed.
4. Run a recovery drill: clone the repo into a temp dir, restore the key from 1Password, run `git-crypt unlock`, confirm `git-crypt status -e` shows decrypted content and `git status --short` is clean.
5. Delete the loose key file from `$HOME` after the drill.
6. On AX41: run the sparse-checkout + tripwire commands so `vault/` cannot be committed locally. Confirm AX41's GitHub credential for the fbrain repo is read-only (deploy key) or removed.

## What's automatable (agent can do once authorized)

- Generate the AX41 sparse-checkout config and pre-commit hook (steps 6).
- Audit AX41's current git remote credential type (`gh auth status`, `git config remote.origin.url`) and recommend the read-only swap.
- Verify the SHA-256 fingerprint of the exported key against what Federico stores in 1Password.
- Document the recovery drill as a runnable script in `launch/recovery-drill.sh`.

## What's NOT automatable

- Exporting the key on Mac (must happen on the machine that holds the key, with Federico's session).
- Writing into 1Password (interactive, Federico-only).
- Hardening the 1Password account (Secret Key, YubiKey, recovery code).
- Deciding if AX41 should ever hold the key (Federico's trust call, defaults to no).

## What breaks if X

| Failure | Impact | Recovery |
|---|---|---|
| Mac dies | None on vault | Clone repo on new machine, retrieve key from 1Password, `git-crypt unlock` |
| AX41 dies | None on vault | Rebuild from GitHub. Vault was never there in plaintext if Mode 1 was followed |
| 1Password cloud breach | Encrypted vault data exposed | Secret Key + master password + Argon2 KDF resist offline attack. Rotate `git-crypt` key proactively if breach confirmed |
| 1Password account takeover (active session hijack) | `git-crypt` key fully exposed | Rotate `git-crypt` key. Treat all historical commits as compromised. May require fresh repo |
| GitHub compromise | Encrypted blobs, paths, file sizes, commit timing exposed | Cannot decrypt content. But any PRIOR plaintext leak in Git history (e.g. yesterday's incident) is permanently exposed and only fixable by repo rewrite + key rotation |
| Hardware token (YubiKey) lost | None on vault, only on 1Password auth | Recover via second registered token or recovery code |
| `git-crypt` key leaked once | Full historical vault compromise, permanently | Generate new key, rotate, rewrite repo history or fork to fresh repo to truly contain |

## Subtle attacks Codex flagged

- `git-crypt` does not hide filenames, paths, file sizes, or commit timing — metadata leakage is real.
- A malicious or over-permissioned AI agent on an unlocked machine can read plaintext like any local process. (Direct relevance: claude/codex sessions on Mac with the vault unlocked.)
- Browser extensions can steal password-manager page content or downloaded key files.
- Clipboard managers can retain copied passphrases or keys.
- Shell history can capture paths or commands referencing the key.
- Git hooks are bypassable; CI leak checks fire after push so any pushed plaintext already reached GitHub.
- Server snapshots and backups can retain plaintext after an AX41 unlock — even `rm` of the key file does not undo what the FS layer captured.
- macOS Spotlight, editor swap files, Time Machine, iCloud Desktop/Documents can copy plaintext working trees outside the encrypted boundary.
- Supply-chain compromise of `git-crypt`, package managers, shell plugins, or repo scripts can exfiltrate the key at unlock time.
- Password-manager recovery flows can be socially engineered (phone number + email reset).
- GitHub OAuth apps and deploy keys often outlive the mental model of who has access — audit periodically.
- If the raw `git-crypt` key leaks once, historical encrypted blobs are decryptable forever.

## Implementation effort

- **Federico-time:** 30-45 minutes total (export, 1Password write, drill, AX41 sparse-checkout, AX41 credential audit).
- **Agent-time:** 15 minutes of follow-up scripting and verification once Federico authorizes.
- **No code shipping required** — this is operational work on existing infrastructure.

## Open question for Federico

Does AX41 ever genuinely need plaintext write access to `vault/`? If yes, Mode 2 from the analysis applies and the leak vector reopens. The default recommendation is **no** — AX41 stays cipher-only with no GitHub write credential for this repo, and any plaintext authoring goes through Mac.
