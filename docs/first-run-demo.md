# First-run demo

Witness V1 includes a deterministic local demo pack so a new user can see the
complete evidence-first flow without preparing a corpus first.

## What the demo installs

The demo writes a small set of local files inside the opened workspace:

- a 2025 API handbook that says the API used port 4100;
- a superseding 2026 API handbook that says the current API uses port 5200;
- an authentication operations source that records bearer tokens and 90-day rotation.

The two API handbooks share one logical source identity but have different
immutable source-version IDs and validity dates. This makes the first-run demo
exercise temporal retrieval and source supersession rather than only exact lookup.

The demo also registers:

- `witness-first-run-demo-v1`, a three-case RAG Lab benchmark covering current
  evidence, exact evidence, and abstention;
- `witness-first-run-prompt-injection-v1`, an Attack Lab manifest that injects
  an untrusted `ATTACK_SUCCEEDED` instruction and checks canonical-corpus and
  citation invariants.

Canonical copies of the demo evaluation dataset and attack manifest are written
to the workspace `demo/` directory for inspection.

## Desktop first-run path

When an opened workspace has no sources, the desktop displays **Load demo & open
Trace**. The action:

1. installs the deterministic demo pack;
2. refreshes Library, Lab, Attack, workspace health, and provider state;
3. asks `What port does the current API use?` through the production Ask pipeline;
4. switches directly to Trace for that real QueryRun.

The demo therefore reaches the same retrieval, reconciliation, sufficiency,
generation, citation validation, and Trace stages as a user corpus.

## Idempotence

Demo files are only rewritten when their content differs. Their identity keys,
contents, and validity dates are fixed, so rerunning the demo does not create
additional source versions. Dataset and attack registration are content-addressed
and are likewise idempotent.

Automated acceptance coverage verifies that the demo survives workspace reopen
with exactly the same source-version identities and registered Lab/Attack assets.
