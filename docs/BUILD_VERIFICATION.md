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

`packaging/github-workflow.yml` is the reviewed workflow template. Copy it to
`.github/workflows/windows.yml` through an account permitted to manage workflows.
The current CLI credential lacks the `workflow` scope, so this activation cannot
be published through that credential. Activation is separate from merging the
security fixes. The workflow uses immutable action commit IDs, hash-verified
installs, offline checks, and read-only permissions for PR builds. Only tag
releases use temporary write permissions for attestations and release assets.

After activation and merge, push a version tag matching the app's version to
build and attest a release. Existing published assets are retained; they are
not retroactively attested or replaced. For a newly attested ZIP:

```powershell
gh attestation verify .\Room-AC-Control-for-hOn-<version>-Windows-x64.zip --repo LuisBadal0/room-ac-control-hon
```

Verification should identify this repository and the workflow's source commit.
Failing verification means provenance has not been established. CI runner
images, the Python installation and build tooling remain trusted inputs; this
project does not claim byte-identical reproducible Windows binaries.

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
certificate or secret is embedded in the workflow template.
