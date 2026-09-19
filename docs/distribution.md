# Windows distribution and update policy

This document defines the V1.1 Windows distribution boundary.

## Current release channel

Witness ships as a current-user NSIS installer produced by GitHub Actions. The
installer bundles the frozen Witness engine and does not require Python.

Every tagged release must:

1. pass the six-job CI matrix;
2. have synchronized Tauri, npm, Rust, Python-package, and Python-runtime
   versions;
3. use a `vX.Y.Z` Git tag matching embedded metadata;
4. pass the installed application smoke;
5. publish `SHA256SUMS.txt`;
6. use checked-in release notes when `RELEASE_NOTES_vX.Y.Z.md` exists.

`tools/check-distribution-metadata.py` verifies the product name, stable app
identifier, publisher metadata, NSIS target/current-user install mode, and that
the configured installer icon is a structurally valid ICO file.

## Code signing plan

V1.1 does not invent or embed a signing identity. Until a certificate or trusted
signing service is provisioned, releases remain unsigned and the README must say
so.

When a signing identity is available:

1. Store signing credentials only in a protected GitHub Environment or trusted
   signing service; never in the repository or workspace.
2. Prefer a hardware/cloud-backed Windows code-signing identity with RFC 3161
   timestamping.
3. Sign the desktop executable and bundled engine before NSIS packaging.
4. Sign the final NSIS installer after packaging.
5. Verify signatures in CI with Windows Authenticode tooling before artifact
   upload/publication.
6. Fail the release if signing was requested but any signature/timestamp
   verification fails.
7. Record certificate subject/thumbprint and timestamp result in the release job
   log, but never private material.

### SmartScreen

SmartScreen reputation is not bypassed. A stable signed publisher identity and
consistent release process are the strategy. Documentation may explain an
unsigned/reputation warning, but Witness should never teach users to disable
SmartScreen globally.

## Icon/product metadata

The stable Windows identity is:

- product: `Witness`;
- application identifier: `com.purysho.witness`;
- publisher label: `Purysho`;
- installer: NSIS, current user.

The release config currently points to `icons/icon.ico`. CI validates the ICO
container and reference. A human release check should still visually inspect the
installed executable, Start menu/search result, taskbar, installer, and
uninstaller at normal Windows scaling. Multi-resolution artwork can be improved
later without changing the application identifier.

## Update policy

### V1.1 behavior

Witness performs **no automatic update checks and no background update network
requests**. Updating is an explicit user action:

1. open the public GitHub Releases page;
2. choose the intended release;
3. download the installer;
4. optionally verify it against `SHA256SUMS.txt`;
5. close Witness and run the installer.

Updating the application must never modify a workspace as part of the update
mechanism. Workspace migration/repair remains an explicit application concern.

### Future signed update channel

An automatic updater is acceptable only after signing is available. A future
implementation should:

- make the first network check user-initiated or explicitly opt-in;
- use HTTPS and signed update metadata;
- verify artifact signature and/or cryptographic digest before execution;
- never send workspace contents, paths, query text, provider settings, or
  identifiers to the update service;
- stage downloads outside the workspace;
- never install while a workspace mutation/job is active;
- require a clear restart/install action unless the user explicitly opts into a
  stronger automatic policy;
- fail closed/offline when metadata, signature, checksum, or network validation
  fails;
- preserve the ability to use Witness indefinitely without network access.

GitHub Releases is the authoritative public release source until a separately
documented signed channel replaces it.
