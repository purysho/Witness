# Witness v1.1.2

## Fixed

- Example paths in the Workspace, Lab and Attack fields showed a Windows drive
  path (`C:\Witness\…`) on macOS and Linux. They now use `~/Witness/…` there.
  The Attack field also showed doubled backslashes on Windows.

## Release checks

- Every release now launches the packaged app on macOS and Linux and checks
  that its bundled engine starts before anything is published.

Packages, platforms and signing status are otherwise as in v1.1.1.
