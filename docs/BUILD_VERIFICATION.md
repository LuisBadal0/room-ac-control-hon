# Build and release verification

## Run reviewed source

Check out the commit you intend to review, install trusted Python for Windows
with Tkinter, and run `tools/Setup.ps1`. This installs the complete
`requirements.lock` with `--require-hashes --only-binary=:all:` before installing
the local project with `--no-deps --no-build-isolation`. The launcher uses the
same verified setup when no portable runtime exists. Python 3.13.13 is used for
the portable build; the dependency lock is for Windows.

`requirements.txt` is package metadata, not the complete installation lock.
Plain `pip install -e .` does not enforce the hashes. The setup helper replaces
installed dependency copies when the lock changes, and verifies dependency
consistency. Python and pip are supplied by your Python installation and are
not covered by the project lock.

## Build a portable executable

Run `tools/Build.ps1`. It installs both runtime and packaging locks, tests the
frozen runtime offline, and writes a ZIP plus `SHA256SUMS.txt` to `releases/`.
`Setup.ps1` alone does not build an executable.

## Build the installers

`tools/build_installers.py` (run by `Build.ps1` when the .NET SDK is installed,
and by CI) unpacks the portable ZIP's app folder and packages exactly those
files into `Room-AC-Control-for-hOn-<version>-Windows-x64.msi` and a WiX bundle,
`...-Windows-x64-Setup.exe`, that installs the same MSI. Both are per-user
installs into `%LOCALAPPDATA%\Programs\Room AC Control` with no elevation, so the
app keeps its `runtime\RoomACControl` layout and its signed in-app updates.
The WiX Toolset is the .NET local tool pinned in `.config/dotnet-tools.json`
(`dotnet tool restore`), and its UI, Util and BootstrapperApplications
extensions are pinned to the same version. The recipes are in
`packaging/installer/`: `RoomACControl.wxs` (the MSI), `InstallerUI.wxs` (its pages, with the
desktop-shortcut checkbox), `Setup.wxs` (the bundle) and `SetupTheme.xml`/`.wxl`
(its window, adapted from WiX's HyperlinkTheme). Keep their `UpgradeCode`s unchanged, or new installers
will no longer upgrade old ones. `SHA256SUMS.txt` lists the ZIP, MSI and
Setup.exe. The installers are not Authenticode-signed.

The runtime's `BUILD-MANIFEST.json` contains the Git commit, whether the source
checkout had changes, hashes of tracked source files, Python/dependency versions,
the executable hash and its Authenticode status. Published CI builds require a
clean checkout. A dirty local build is explicitly identified. Builds from a
source ZIP without Git metadata cannot generate this provenance manifest;
use a Git checkout to build the portable release.

Compare the downloaded ZIP's SHA-256 with the release's `SHA256SUMS.txt` using
`Get-FileHash -Algorithm SHA256`. This detects an altered download, provided the
checksum came from a trusted source. It does not independently authenticate the
publisher or prove correspondence to the source. Inspect the executable with
`Get-AuthenticodeSignature` to check its signature status.

## CI and attestations

`.github/workflows/windows.yml` is the active Windows CI workflow. It runs
offline tests, UI checks and portable packaging for pull requests and pushes to
`main`. The workflow uses immutable action commit IDs, hash-verified installs,
and read-only permissions for PR builds. Only the release job, which runs after
pushes to `main` and version tags, uses temporary write permissions for
attestations and release assets. Editing workflows through the
CLI requires a credential permitted to manage them; the GitHub web editor is
also supported. The workflow file stores no credentials; the release job reads
the update-signing key from the `UPDATE_SIGNING_KEY` secret.

Releases are automatic: when a merge to `main` carries an app version with no
release yet, CI builds, attests and publishes `v<version>` with the ZIP, the MSI,
the Setup.exe and `SHA256SUMS.txt`. Bump the version in the PR to release it; merges that keep the
current version only build. Pushing a matching `v<version>` tag also works.
Existing published assets are retained; they are not retroactively attested or
replaced. For a newly attested ZIP (the MSI and Setup.exe verify the same way):

```powershell
gh attestation verify .\Room-AC-Control-for-hOn-<version>-Windows-x64.zip --repo LuisBadal0/room-ac-control-hon
```

Verification should identify this repository and the workflow's source commit.
Failing verification means provenance has not been established. CI runner
images, the Python installation and build tooling remain trusted inputs; this
project does not claim byte-identical reproducible Windows binaries.

## In-app update signing

Each release also publishes `update.json` (version, tag, ZIP name, size and
SHA-256) and `update.json.sig`, an RSA-PSS SHA-256 signature. The release job
signs with the `UPDATE_SIGNING_KEY` repository secret. Before publishing, it
verifies the signature against `packaging/update-signing-key.pub` at the release
commit, and it refuses to publish when the secret is missing. The app embeds the
same public key (`room_ac_control.updates.PUBLIC_KEY`, kept equal to the file by
`tests/test_updates.py`) and verifies with `awscrt`, which it already ships, so
no extra dependency is needed. To check a release by hand:

```bash
openssl pkey -pubin -in packaging/update-signing-key.pub -out key.spki.pub
openssl dgst -sha256 -verify key.spki.pub -sigopt rsa_padding_mode:pss -sigopt rsa_pss_saltlen:32 -signature update.json.sig update.json
```

To rotate the key, ship a release that still verifies with the old key but
embeds the new public key. Change the secret only after that release. Apps
that skip that release must download the next one manually. The offline test
fixtures in `tests/fixtures` are signed with a throwaway key; regenerate them with
`tests/fixtures/make_update_fixtures.py`.

## Optional Authenticode signing

Use a trusted code-signing certificate with a private key in the current user's
Windows certificate store. Set `ROOM_AC_SIGNING_CERT_THUMBPRINT` for the build
process; optionally set `ROOM_AC_TIMESTAMP_SERVER` to your certificate provider's
approved HTTPS timestamp endpoint. `tools/Sign-Executable.ps1` signs before the
ZIP/checksum is produced and requires a valid signature. Without a certificate,
the build remains unsigned and reports `NotSigned`; it does not manufacture a
self-signed certificate or change Windows trust settings. The signing path
requires verification with your actual certificate before a signed release.

Never commit certificates, private keys, credentials or signing secrets. No
certificate or secret is embedded in the workflow.
