# Witness post-v1.1 observation and V1.1.1 triage

Observation started: 2026-09-19

Witness v1.1.0 is published. This period intentionally pauses feature expansion while the released build is treated as a real user would treat it. The goal is to gather reproducible evidence before assigning work to V1.1.1 or V1.2.

## Rules

1. Do not create a V1.1.1 item from preference, polish, or speculative optimization.
2. Reproduce a reported problem against the published v1.1.0 installer when practical.
3. Preserve the workspace/provenance boundary while reproducing failures.
4. Record the smallest reproducible case, environment, relevant Trace/health information, and measured timing where applicable.
5. A V1.1.1 fix should be bounded and regression-oriented. New capability belongs in V1.2 unless it is required to repair a concrete V1.1.0 defect.

## Classification

### V1.1.1

Use V1.1.1 for a reproducible defect or regression in the shipped V1.1.0 behavior, especially:

- public installer/download/checksum failures;
- launch, first-run, reopen, backup/restore, uninstall, or workspace-recovery regressions;
- provenance, citation, historical-trace, or protected-state correctness failures;
- a retrieval/evidence regression against the fixed V1.1 quality dataset;
- a material performance regression against a recorded V1.1 baseline when it affects normal use;
- a bounded compatibility defect affecting an existing V1 workspace.

A V1.1.1 change should avoid new architecture, new product surfaces, and unnecessary schema changes.

### V1.2

Use V1.2 for intentional capability expansion or broader redesign, including:

- broader multimodal ingestion such as standalone images or embedded Office images;
- new provider families or network-backed provider behavior;
- automatic updating/signing infrastructure once a trusted identity exists;
- broad performance work without a reproduced V1.1.0 regression;
- new collaboration/cloud/account behavior;
- UX redesign that is not required to repair a concrete defect.

## Released baselines

### Distribution

- Version: v1.1.0
- Windows installer: `Witness_1.1.0_x64-setup.exe`
- Published size: 31,615,762 bytes
- Published SHA-256: `d092c31bc2888fa8d4d35e2cb4a26af7a925fe4a4bb96c496e4524f952fc267c`
- Installer type: current-user NSIS, unsigned
- Update behavior: manual; no background update check

The post-release observation workflow downloads these exact public assets from GitHub Releases, independently rehashes the installer, and runs the existing installed-package smoke against those downloaded bytes.

First public-artifact observation, run `35449322964`, passed on GitHub's Windows Server 2025 hosted runner:

- installer and checksum asset fetch: 1.938 s;
- downloaded size: 31,615,762 bytes;
- downloaded SHA-256 matched the published checksum and recorded release hash;
- install -> desktop launch -> bundled-engine RPC -> normal close -> uninstall: 12.628 s.

These hosted-runner/network timings are observation data, not fixed performance thresholds.

### Large corpus

V1.1 stress baseline, run `35431097813`:

- 2,000 files;
- 8,569 chunks;
- ~50 MB workspace database;
- ~18 files/second import on the hosted Windows runner;
- initial query ~0.82 s;
- reopen ~0.012 s;
- reopen query ~0.23-0.25 s;
- derived-index repair ~33.6 s;
- five reopen/query cycles remained healthy;
- cancellation rollback and protected-state invariants passed.

The ~33.6 s repair time is a watch item, not a V1.1.1 defect by itself. It becomes a patch candidate only if observation shows a material regression or normal-user failure.

### Retrieval/evidence quality

V1.1 quality baseline, run `35439951846`:

- immutable dataset fingerprint `2f427210f2f8349e63ce8a5c3241f53727c0ab4a3e5136f7016a146a61aef513`;
- corpus fingerprint `177bfdcc4e5e689fc38b211d265de43e43fd559ef2ccb53ccfbc592134529955`;
- 8/8 routed cases passed;
- Recall@K 1.0;
- MRR 1.0;
- citation precision 1.0;
- state accuracy 1.0;
- abstention correctness 1.0;
- contradiction handling 1.0;
- expected-answer fragment accuracy 1.0;
- unsupported-claim rate 0.0.

## Observation log

| Date | Signal | Evidence | Classification |
| --- | --- | --- | --- |
| 2026-09-19 | Repository issue queue | No open GitHub issues were present at observation start. | No patch candidate |
| 2026-09-19 | Main CI | Full six-job post-release cleanup CI was green. | No patch candidate |
| 2026-09-19 | Public release artifact | Run `35449322964` independently downloaded the exact public installer/checksum, verified 31,615,762 bytes and SHA-256 `d092c31b...`, then passed install/launch/bundled-engine RPC/normal-close/uninstall in 12.628 s. | No patch candidate |
| 2026-09-19 | Derived-index repair | ~33.6 s at the 2,000-file V1.1 baseline. Correctness remained healthy. | Watch only; no regression established |
| 2026-09-19 | Unsigned installer | Known and disclosed V1.1 distribution limitation; no signing identity is provisioned. | Operational/V1.2 dependency, not V1.1.1 |

## V1.1.1 candidate register

No item qualifies at observation start or after the first public-artifact smoke.

Add an item only after a reproducible defect/regression is recorded. For each candidate capture:

- symptom and user impact;
- exact reproduction steps;
- released version and OS;
- public installer or development build;
- relevant workspace health / Trace identifiers without private source content;
- expected vs actual result;
- frequency;
- measured baseline comparison if performance-related;
- smallest bounded fix;
- regression test required before merge.

## Exit from observation

Move work into V1.1.1 only when one or more bounded regressions are reproduced. If the released build remains healthy and the remaining requests are capability expansion, close the observation period without manufacturing a patch and move those requests to V1.2 planning.
