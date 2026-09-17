# ADR 0001 — Tauri desktop + Python evidence engine

**Status:** Accepted

## Context
Witness needs a distinctive desktop UI, reliable Windows packaging, local filesystem controls, and access to the Python RAG/parser/evaluation ecosystem.

## Decision
Use a Tauri 2 / React / TypeScript desktop application with a Rust host supervising a Python 3.12 engine sidecar.

Communication uses a versioned structured local IPC protocol rather than a public localhost HTTP server.

## Consequences
- UI and OS boundary remain small and typed.
- Python owns evidence/retrieval logic and can be tested headlessly.
- Packaging is more involved than a single-language app, so packaged-sidecar smoke testing is mandatory.
- No retrieval logic is permitted in the frontend.
