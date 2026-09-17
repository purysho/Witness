# Witness contracts

Versioned schemas shared across the desktop host and Python engine live here.

The engine-side Pydantic RPC/config models are the initial source of truth. CI will export JSON Schema into `json-schema/` and generate TypeScript declarations into `generated/`.

Contract rules:
- explicit protocol/schema version;
- additive compatible changes where possible;
- breaking changes require a version bump;
- no provider-specific SDK objects;
- no arbitrary shell/command RPC;
- typed errors and cancellable long-running jobs.
