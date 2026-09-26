# Witness v1.1.1

Witness now ships for macOS and Linux as well as Windows. The engine and
application are unchanged from v1.1.0.

## Downloads

- **Windows (x64):** current-user NSIS installer, as before.
- **macOS (Apple Silicon):** disk image.
- **Linux (x86_64):** AppImage, and a `.deb` package for Debian and Ubuntu.

Every package bundles the frozen Witness engine, so Python is not required.
Each build smoke-tests the frozen engine before packaging, and one
`SHA256SUMS.txt` covers every file in the release.

## Also in this release

- The application icon is now the Witness mark used across Purysho, at every
  size each platform asks for. The previous Windows icon was a single 32×32
  placeholder.
- Releases can be published from a manual workflow run given a version, as
  well as from a tag.

## Not yet code-signed

These builds are unsigned, so Windows SmartScreen may ask you to confirm the
installer, and macOS may need you to Control-click the app and choose
**Open** the first time. Signing switches on automatically once signing
credentials are added to the repository.
