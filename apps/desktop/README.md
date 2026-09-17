# Desktop application

This directory will contain the Witness Tauri 2 desktop shell and React/TypeScript interface.

Responsibilities:
- Library / Ask / Trace / Graph / Lab / Attack presentation;
- user interaction and visualization;
- Tauri command calls and engine event handling;
- no retrieval/evidence domain logic.

The Rust host under `src-tauri/` will own sidecar lifecycle, OS file permissions, secret/environment resolution, and packaging boundaries.
