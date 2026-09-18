# Provider configuration

Witness V1 keeps provider configuration reproducible and secret-free.

## Workspace settings

The workspace persists only non-secret provider choices:

- deterministic text-embedding dimensions;
- workspace visual retrieval mode (`off` or deterministic hash);
- workspace visual embedding dimensions;
- an update timestamp.

The schema has no API-key, token, credential, endpoint-password, or secret-value
column. Unknown RPC parameters such as `api_key` are ignored rather than stored.

Reranking and generation remain explicit fixed V1 baselines:

- `deterministic-token-reranker:v1`;
- `deterministic-extractive-generator:v1`.

Those identities remain visible in Trace and Lab configuration snapshots.

## Provider identity and reindexing

Embedding provider identity includes its configured dimensions. Changing the text
embedding dimensions therefore creates a new provider identity instead of silently
mixing vectors from incompatible configurations. Existing vectors remain available
for historical/replay purposes; the active provider reports `reindex_required`
until its projection has been rebuilt from canonical chunks.

The same rule applies to workspace visual hash embeddings. Workspace Health and
the provider panel expose when a derived projection needs repair.

## Environment visual override

`WITNESS_VISUAL_PROVIDER` remains an explicit environment-level override for
visual retrieval. When present, the desktop shows the visual provider as
`environment` and disables workspace visual controls. The saved workspace values
remain visible but are not misrepresented as active.

Supported environment values remain:

- `hash` — deterministic plumbing provider;
- `openclip` — optional semantic OpenCLIP provider when the vision dependencies
  are installed;
- unset — use the workspace visual setting.

Environment-backed secrets are not copied into workspace configuration, traces,
Lab runs, exports, or provider snapshots.

## Release baseline

The packaged V1 release guarantees the dependency-free deterministic providers.
Optional semantic providers remain explicit extras; Witness does not claim a
semantic model is available when its optional dependency/model is absent.
