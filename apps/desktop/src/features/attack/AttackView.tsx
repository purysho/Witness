import { useMemo, useState } from "react";
import type {
  AttackManifestSummary,
  AttackRunListItem,
  AttackRunResult,
  EvalConfigInput,
  EvalDatasetSummary,
  RetrievalMode,
} from "../../../../../contracts/generated/rpc";

const modes: RetrievalMode[] = ["lexical", "dense", "hybrid", "routed"];

interface Props {
  workspaceReady: boolean;
  busy: boolean;
  datasets: EvalDatasetSummary[];
  manifests: AttackManifestSummary[];
  runs: AttackRunListItem[];
  result: AttackRunResult | null;
  onLoadManifest: (path: string) => void;
  onRun: (
    manifestFingerprint: string,
    datasetFingerprint: string,
    config: EvalConfigInput,
  ) => void;
  onLoadRun: (attackRunId: string) => void;
  onInspectCase: (side: "clean" | "attacked", caseId: string) => void;
  onExport: (attackRunId: string, format: "json" | "csv") => void;
}

function delta(value: number | null) {
  if (value === null) return "—";
  return (value >= 0 ? "+" : "") + value.toFixed(3);
}

export function AttackView({
  workspaceReady,
  busy,
  datasets,
  manifests,
  runs,
  result,
  onLoadManifest,
  onRun,
  onLoadRun,
  onInspectCase,
  onExport,
}: Props) {
  const [manifestPath, setManifestPath] = useState("");
  const [manifestFingerprint, setManifestFingerprint] = useState("");
  const [datasetFingerprint, setDatasetFingerprint] = useState("");
  const [mode, setMode] = useState<RetrievalMode>("routed");
  const [topK, setTopK] = useState(10);
  const [rerank, setRerank] = useState(true);

  const manifest = manifestFingerprint || manifests[0]?.manifest_fingerprint || "";
  const dataset = datasetFingerprint || datasets[0]?.dataset_fingerprint || "";
  const selectedManifest = useMemo(
    () => manifests.find((item) => item.manifest_fingerprint === manifest) ?? null,
    [manifests, manifest],
  );

  const config: EvalConfigInput = {
    name: "Attack · " + mode,
    retrieval_mode: mode,
    top_k: topK,
    candidate_pool: Math.max(30, topK),
    rerank_pool: Math.max(20, topK),
    rrf_k: 60,
    rerank,
    chunk_max_chars: 1200,
  };

  return (
    <div className="lab-layout">
      <section className="panel lab-main">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">ATTACK LAB</span>
            <h2>Break the evidence pipeline safely</h2>
          </div>
          <span className="count">
            {selectedManifest
              ? selectedManifest.mutation_count + " mutations"
              : "no manifest"}
          </span>
        </div>

        <div className="lab-dataset-row">
          <label className="field grow">
            <span>Attack manifest JSON</span>
            <input
              value={manifestPath}
              onChange={(event) => setManifestPath(event.target.value)}
              placeholder="C:\\Witness\\attacks\\prompt-injection.json"
            />
          </label>
          <button
            className="secondary"
            disabled={busy || !workspaceReady || !manifestPath.trim()}
            onClick={() => onLoadManifest(manifestPath)}
          >
            Register attack
          </button>
        </div>

        <div className="lab-config-grid">
          <article className="lab-config-card">
            <span className="eyebrow">ATTACK</span>
            <label className="field">
              <span>Immutable manifest</span>
              <select
                value={manifest}
                onChange={(event) => setManifestFingerprint(event.target.value)}
              >
                {manifests.length === 0 && <option value="">No manifests registered</option>}
                {manifests.map((item) => (
                  <option key={item.manifest_fingerprint} value={item.manifest_fingerprint}>
                    {item.name + " · " + item.manifest_fingerprint.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          </article>

          <article className="lab-config-card">
            <span className="eyebrow">BENCHMARK</span>
            <label className="field">
              <span>Dataset snapshot</span>
              <select
                value={dataset}
                onChange={(event) => setDatasetFingerprint(event.target.value)}
              >
                {datasets.length === 0 && <option value="">No datasets registered</option>}
                {datasets.map((item) => (
                  <option key={item.dataset_fingerprint} value={item.dataset_fingerprint}>
                    {item.name + " · " + item.case_count + " cases"}
                  </option>
                ))}
              </select>
            </label>
          </article>

          <article className="lab-config-card lab-shared">
            <span className="eyebrow">PIPELINE</span>
            <label className="field">
              <span>Retrieval mode</span>
              <select value={mode} onChange={(event) => setMode(event.target.value as RetrievalMode)}>
                {modes.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Top K</span>
              <input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(event) => setTopK(Math.max(1, Math.min(50, Number(event.target.value) || 1)))}
              />
            </label>
            <label className="lab-check">
              <input
                type="checkbox"
                checked={rerank}
                onChange={(event) => setRerank(event.target.checked)}
              />
              deterministic rerank
            </label>
            <button
              className="primary"
              disabled={busy || !workspaceReady || !manifest || !dataset}
              onClick={() => onRun(manifest, dataset, config)}
            >
              {busy ? "Running attack…" : "Run clean vs attacked"}
            </button>
          </article>
        </div>

        {result ? (
          <>
            <div className="lab-section-title">
              <div>
                <span className="eyebrow">ISOLATION</span>
                <h3>{result.run.attack_name}</h3>
              </div>
              <div className="lab-run-actions">
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => onExport(result.run.attack_run_id, "json")}
                >
                  Export JSON
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => onExport(result.run.attack_run_id, "csv")}
                >
                  Export CSV
                </button>
              </div>
            </div>
            <div className="model-judged-note">
              <strong>Canonical corpus</strong>
              <span>{result.run.canonical_corpus_fingerprint.slice(0, 16)}</span>
              <strong>Attacked corpus</strong>
              <span>{result.run.attacked_corpus_fingerprint.slice(0, 16)}</span>
            </div>

            <div className="lab-section-title">
              <div>
                <span className="eyebrow">INVARIANTS</span>
                <h3>
                  {result.invariants.filter((item) => item.status === "FAIL").length +
                    " failures"}
                </h3>
              </div>
            </div>
            <div className="lab-case-list">
              {result.invariants.map((item) => (
                <article className="lab-case" key={item.invariant_id}>
                  <div>
                    <strong>{item.invariant_id}</strong>
                    <p>{item.detail}</p>
                  </div>
                  <div className="lab-case-states">
                    <span>{item.status}</span>
                    <span>{item.kind}</span>
                  </div>
                </article>
              ))}
            </div>

            <div className="lab-section-title">
              <div>
                <span className="eyebrow">CASE DIFF</span>
                <h3>Clean vs attacked</h3>
              </div>
            </div>
            <div className="lab-case-list">
              {result.cases.map((item) => (
                <article className="lab-case" key={item.case_id}>
                  <div>
                    <strong>{item.case_id}</strong>
                    <p>{item.question}</p>
                  </div>
                  <div className="lab-case-states">
                    <span>{"clean · " + (item.clean_state ?? "ERROR")}</span>
                    <span>{"attacked · " + (item.attacked_state ?? "ERROR")}</span>
                    <span>{"Δ recall " + delta(item.recall_delta)}</span>
                    <span>{"Δ precision " + delta(item.precision_delta)}</span>
                    <span>{"Δ citations " + delta(item.citation_coverage_delta)}</span>
                    <span>{"evidence +" + item.added_evidence_count}</span>
                    <span>{"evidence −" + item.removed_evidence_count}</span>
                    <span>{"rank moved " + item.rank_changed_count}</span>
                  </div>
                  <div className="attack-answer-diff">
                    <div>
                      <strong>Clean answer</strong>
                      <p>{item.clean_answer_text || "No answer text."}</p>
                    </div>
                    <div>
                      <strong>Attacked answer</strong>
                      <p>{item.attacked_answer_text || "No answer text."}</p>
                    </div>
                  </div>
                  <div className="lab-case-actions">
                    {item.clean_query_run_id && (
                      <button className="secondary" onClick={() => onInspectCase("clean", item.case_id)}>
                        Clean trace
                      </button>
                    )}
                    {item.attacked_query_run_id && (
                      <button className="secondary" onClick={() => onInspectCase("attacked", item.case_id)}>
                        Attacked trace
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="empty lab-empty">
            Attack Lab clones the current corpus, injects adversarial evidence into the clone only, then runs the same benchmark against clean and attacked pipelines.
          </div>
        )}
      </section>

      <aside className="panel lab-sidebar">
        <span className="eyebrow">ATTACK HISTORY</span>
        <h2>Persisted experiments</h2>
        <div className="lab-run-list">
          {runs.length === 0 ? (
            <div className="empty">No attack runs yet.</div>
          ) : (
            runs.slice(0, 12).map((run) => (
              <article key={run.attack_run_id}>
                <div>
                  <strong>{run.attack_name}</strong>
                  <span>{run.status + " · " + run.snapshot_id.slice(0, 10)}</span>
                </div>
                <code>{run.attack_run_id.slice(0, 10)}</code>
                <small>{run.started_at}</small>
                <button
                  className="secondary"
                  disabled={busy || run.status !== "completed"}
                  onClick={() => onLoadRun(run.attack_run_id)}
                >
                  Open run
                </button>
              </article>
            ))
          )}
        </div>
        <div className="lab-snapshot">
          <strong>Hard boundary</strong>
          <span>SQLite backup snapshot</span>
          <span>Separate attack artifact namespace</span>
          <span>Canonical fingerprint rechecked</span>
          <span>Production Ask + Trace reused</span>
        </div>
      </aside>
    </div>
  );
}
