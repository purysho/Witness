# Large-corpus stress testing

Witness V1.1 includes a reproducible mixed-format stress harness for robustness
and baseline measurement before performance changes are made.

## Full local run

Install the engine in editable mode, then run:

```powershell
python -m pip install -e engine
python tools/stress-workspace.py --json-out stress-result.json
```

The default run creates **2,000 files** across Markdown, text, HTML, CSV, source
code, DOCX, PPTX, XLSX, and searchable PDF. Every 50th file is enlarged by a
20x content multiplier.

To retain the generated corpus and workspace:

```powershell
python tools/stress-workspace.py --root .stress-run --json-out .stress-run.json
```

A useful smaller development run is:

```powershell
python tools/stress-workspace.py --files 180 --large-every 18 --reopen-cycles 3
```

## GitHub Actions benchmark

The **Stress Benchmark** workflow can be started manually from GitHub Actions.
Its default inputs run the same 2,000-file workload on Windows and upload
`stress-result.json` as a workflow artifact.

Inputs allow the corpus size, base document size, large-document frequency,
large-document multiplier, and reopen-cycle count to be changed without editing
the repository.

## What the harness measures

The JSON report records:

- corpus generation time and format distribution;
- import time and files/second;
- canonical source-version and chunk counts;
- SQLite/WAL workspace bytes;
- peak traced Python allocations during import;
- workspace health after import;
- evidence/query timing;
- derived-index repair time and protected-state preservation;
- deterministic cancellation rollback;
- repeated reopen time, health, and query evidence.

The cancellation check uses a separate workspace and interrupts a 600-block
source only after partial chunk indexing has begun. The check passes only if all
partial source/chunk state is rolled back and the workspace remains healthy.

The repair check deliberately deletes the disposable FTS projection, requires
Witness to report a repairable workspace, rebuilds the projection, and verifies
that the protected-state fingerprint is unchanged.

## CI policy

Normal CI runs a small 18-file corpus covering every stress format twice. It
checks invariants, **not absolute speed**. Raw timing varies too much across
GitHub-hosted machines to be a safe correctness gate.

Do not introduce hard performance thresholds until several comparable baseline
reports exist. When thresholds are added, prefer regression ratios for stable
measurements such as:

- import files/second;
- reopen time;
- query time;
- repair time;
- database bytes per source/chunk;
- peak Python allocations per source/chunk.

Keep raw baseline JSON out of the repository unless it represents a deliberate,
documented release benchmark.


## V1.1 baseline — 2026-09-19

The first default Windows benchmark completed successfully in GitHub Actions
(Stress Benchmark run `35431097813`).

| Measurement | Result |
| --- | ---: |
| Files | 2,000 |
| Large documents | 40 |
| Source versions | 2,000 |
| Chunks | 8,569 |
| Workspace database | 49,999,872 bytes |
| Corpus generation | 11.42 s |
| Import | 110.91 s |
| Import throughput | 18.03 files/s |
| Initial query | 0.82 s |
| Reopen time | 0.0115–0.0127 s |
| Reopen query | 0.231–0.253 s |
| Derived-index repair | 33.58 s |
| Peak traced Python allocations | 3,673,385 bytes |

Correctness checks all passed:

- workspace health remained `healthy` after import;
- query retrieval returned 10 evidence items;
- cancellation occurred after 650 checks and rolled back completely;
- the cancellation workspace remained healthy;
- deliberately removed FTS state was detected as `repairable`;
- repair returned the workspace to `healthy`;
- the protected-state fingerprint was unchanged by repair;
- five consecutive reopen/query cycles remained healthy.

The 33.58-second repair time is the clearest optimization candidate from this
baseline, but it is not a V1.1 correctness blocker. Future performance work
should compare against this report rather than introducing an unmeasured
rewrite.
