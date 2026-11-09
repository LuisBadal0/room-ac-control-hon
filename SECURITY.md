# Security and privacy

## Password storage and authentication

**Remember me is off by default for new sign-ins.** Enabling it stores your actual
hOn email and password, together with program preferences, in
`%LOCALAPPDATA%\RoomACControl\state.dpapi`. Windows DPAPI encrypts this file for
your Windows user account. Session tokens are kept in memory, not saved to disk.

DPAPI is not protection against malware or other programs running as your
Windows user: those programs can decrypt the saved password. The password also
exists in process memory during authentication. Only enable automatic sign-in
on a Windows account you trust. Existing remembered accounts retain their
previous opt-in. **Sign out** removes saved credentials and resets Remember me;
it retains program preferences. If saved data cannot be decrypted, the app
requires sign-in rather than falling back to plaintext storage.

Credentials are passed to the third-party **pyhOn** library, which authenticates
with hOn over HTTPS. You therefore trust both the app and its dependencies with
your credentials. The current integration uses password-based authentication;
it does not claim to implement token-only remembered sign-in.

## Private vulnerability reports

GitHub private vulnerability reporting is enabled for this repository. Submit
reports directly through the [private security report form](https://github.com/LuisBadal0/room-ac-control-hon/security/advisories/new).
The repository owner is [LuisBadal0](https://github.com/LuisBadal0).

Never post passwords, tokens, device serial numbers, saved state files or raw
cloud responses in public issues. A private report should explain the affected
version, reproduction steps and impact using dummy credentials where possible.
Do not send your real password or encrypted state file even in a private report.

## Dependency and binary verification

Supported setup/build scripts install a complete Windows dependency lock with
SHA-256 verification and wheels only. They install local source separately with
dependency resolution and isolated build downloads disabled. See
[build verification](docs/BUILD_VERIFICATION.md). Python, pip, Windows and the
upstream packages themselves remain part of the trust boundary. Hashes ensure
approved artifacts are used; they do not prove those artifacts are harmless.

Portable releases include `SHA256SUMS.txt` and a `BUILD-MANIFEST.json` describing
the source commit, source hashes, dependency versions and signature status.
A local manifest/checksum is publisher-provided information, not an independent
proof that a binary corresponds to its source. Older releases are unsigned and
have no build attestation. New local builds also remain unsigned unless a valid
code-signing certificate is supplied.

The active Windows workflow pins actions to full commit SHAs and attests each
release's ZIP, MSI and Setup.exe with GitHub build provenance. A PR build or
local build does not create a release attestation. Verify an attested release
file with `gh attestation verify <file> --repo LuisBadal0/room-ac-control-hon`.
Attestation establishes build provenance, not a complete security audit or
byte-for-byte reproducibility.

## Diagnostics and network behavior

Diagnostics are limited to the last 100 events in memory: UTC timestamps,
predefined event codes and approved error categories. They contain no exception
messages/tracebacks, email, password, tokens, device names/identifiers, local
paths, authentication URLs or raw cloud payloads. They are cleared on exit.
Potentially sensitive third-party logging is suppressed without globally
disabling application logging.

Use **Export diagnostics** on the login screen or **Diagnostics** in the Updates window
to choose a local JSON file. Nothing is automatically written or uploaded.
Review the report before sharing; event times reveal when failures happened.

The app uses the hOn cloud for authentication, status and control. It runs no
local network server, opens no router ports and collects no telemetry.

The app, portable or installed, also contacts GitHub to check for updates:
shortly after it starts and about once a day, unless **Check for updates
automatically** is turned off in the Updates window. A check downloads only
`update.json` and its signature from this repository's latest release. It sends
no account, device or usage information beyond what any HTTPS request reveals
(IP address and a fixed `RoomACControl-Updater` user agent). An update is
installed only after the person clicks **Update**, and only if:

- `update.json` verifies with RSA-PSS SHA-256 against the public key built into
  the app. The private key exists only as the `UPDATE_SIGNING_KEY` CI secret
  and an offline backup kept by the maintainer.
- its version is newer than the installed one, so a signed older release cannot
  downgrade the app;
- every downloaded file matches the size and SHA-256 signed in `update.json`.
  A portable copy downloads the ZIP. A copy installed with the MSI downloads
  the MSI, and one installed with Setup.exe downloads the MSI and Setup.exe.
- the new version passes its own `--self-test`, including the updater's
  signature check, before anything is replaced. A portable copy unpacks the
  ZIP next to the current version, refusing unsafe paths. An installed copy
  unpacks the app from the MSI into a scratch folder with `msiexec /a`, which
  installs and registers nothing.

Two small helpers in `%LOCALAPPDATA%\RoomACControl\updates` finish the update
after the app has exited. Paths reach them only through environment variables.

- `apply-update.cmd`, for a portable copy, renames `runtime\RoomACControl` to
  `RoomACControl.old` and the new copy into place, then starts it. If either
  rename fails, it restores the previous folder.
- `install-update.cmd`, for an installed copy, runs the verified installer
  silently: `msiexec /i` for an MSI install, or Setup.exe with `/quiet`. Both
  are per-user and need no administrator rights. Windows Installer rolls back
  a failed installation, so the previous version stays. The installer's log,
  `install.log`, stays in that folder after a failure and is removed after the
  next successful update. It lists local paths, so review it before sharing.

Someone who controls both the signing key and the release page could ship a
malicious update; the key is kept separate from the GitHub account credentials
for that reason. Source checkouts and the offline preview never check or
install updates.

Menus, timer previews, status refresh and offline tests do not operate the AC.
Live **Set** and **Stop** timer buttons, and the **Schedules** window, create,
update, pause or cancel schedules in hOn's authenticated cloud scheduling
service. Scheduled commands include the
AC identifier and selected settings; they are held by hOn and survive closing
the application or signing out. Timer status and returned command payloads
stay in process memory and are excluded from diagnostics. Use **Stop** to
cancel a saved timer. The PC does not run a local timer scheduler. See the
[user guide](docs/USER_GUIDE.md).
