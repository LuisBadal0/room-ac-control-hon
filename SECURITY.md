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

The active Windows workflow pins actions to full commit SHAs and attests tagged
release ZIPs with GitHub build provenance. A PR build or local build does not
create a release attestation. Verify an attested
release with `gh attestation verify <zip> --repo LuisBadal0/room-ac-control-hon`.
Attestation establishes build provenance, not a complete security audit or
byte-for-byte reproducibility.

## Diagnostics and network behavior

Diagnostics are limited to the last 100 events in memory: UTC timestamps,
predefined event codes and approved error categories. They contain no exception
messages/tracebacks, email, password, tokens, device names/identifiers, local
paths, authentication URLs or raw cloud payloads. They are cleared on exit.
Potentially sensitive third-party logging is suppressed without globally
disabling application logging.

Use **Export diagnostics** on the login screen or **Diagnostics** in All functions
to choose a local JSON file. Nothing is automatically written or uploaded.
Review the report before sharing; event times reveal when failures happened.

The app uses the hOn cloud for authentication, status and control. It runs no
local network server, opens no router ports and collects no telemetry.
Menus, status refresh and offline tests do not operate the AC. Enabled on/off
timers may send power commands after sign-in when their saved time is due.
Timers are encrypted per account and AC, run only while the app is signed in
and the PC is awake, and skip missed times. See the [user guide](docs/USER_GUIDE.md).
