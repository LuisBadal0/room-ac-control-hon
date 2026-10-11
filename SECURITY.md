# Security and privacy

The controller stores remembered sign-in and program settings in `%LOCALAPPDATA%\RoomACControl\state.dpapi`, encrypted with Windows DPAPI for the current Windows user. Session tokens remain in memory. The application does not run a network server, open router ports or collect telemetry.

Never include your password, tokens, serial number, saved state file, or a raw hOn response in a public issue. For a suspected credential disclosure, use a repository maintainer's private contact or GitHub's private vulnerability reporting when available; post only a sanitized description publicly.

Sign out to remove remembered credentials. The Windows user account remains the trust boundary: another program running as that user may access data protected for that account.
