import { useMemo, useState } from "react";
import type {
  EvalConfigInput,
  EvalDatasetSummary,
  EvalRunSummary,
  LabComparison,
  RetrievalMode,
} from "../../../../../contracts/generated/rpc";

const modes: RetrievalMode[] = ["lexical", "dense", "hybrid", "routed"];

function metricLabel(name: string) {
  return name.replaceAll("_", " ");
}

function metricValue(value: number | null) {
  return value === null ? "—" : value.toFixed(3);
}

interface Props {
  workspaceReady: boolean;
  busy: boolean;
  datasets: EvalDatasetSummary[];
  runs: EvalRunSummary[];
  comparison: LabComparison | null;
  exportPath: string | null;
  onLoadDataset: (path: string) => void;
  onRunAB: (
    datasetFingerprint: string,
    configA: EvalConfigInput,
    configB: EvalConfigInput,
  ) => void;
  onInspectCase: (runId: string, caseId: string) => void;
  onExport: (runId: string, format: "json" | "csv") => void;
}

export function LabView({
  workspaceReady,
  busy,
  datasets,
  runs,
  comparison,
  exportPath,
  onLoadDataset,
  onRunAB,
  onInspectCase,
  onExport,
}: Props) {
  const [datasetPath, setDatasetPath] = useState("");
  const [selectedFingerprint, setSelectedFingerprint] = useState("");
  const [modeA, setModeA] = useState<RetrievalMode>("hybrid");
  const [modeB, setModeB] = useState<RetrievalMode>("routed");
  const [topK, setTopK] = useState(10);
  const [rerankA, setRerankA] = useState(true);
  const [rerankB, setRerankB] = useState(true);

  const selected = selectedFingerprint || datasets[0]?.dataset_fingerprint || "";
  const selectedDataset = useMemo(
    () => datasets.find((item) => item.dataset_fingerprint === selected) ?? null,
    [datasets, selected],
  );

  function makeConfig(name: string, retrievalMode: RetrievalMode, rerank: boolean): EvalConfigInput {
    return {
      name,
      retrieval_mode: retrievalMode,
      top_k: topK,
      candidate_pool: Math.max(30, topK),
      rerank_pool: Math.max(20, topK),
      rrf_k: 60,
      rerank,
      chunk_max_chars: 1200,
    };
  }

  return (
    <div className="lab-layout">
      <section className="panel lab-main">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">RAG LAB</span>
            <h2>Measure the evidence pipeline</h2>
          </div>
          <span className="count">
            {selectedDataset ? selectedDataset.case_count + " cases" : "no dataset"}
          </span>
        </div>

        <div className="lab-dataset-row">
          <label className="field grow">
            <span>Evaluation dataset JSON</span>
            <input
              value={datasetPath}
              onChange={(event) => setDatasetPath(event.target.value)}
              placeholder="C:\Witness\benchmarks\core-v1.json"
            />
          </label>
          <button
            className="secondary"
            disabled={busy || !workspaceReady || !datasetPath.trim()}
            onClick={() => onLoadDataset(datasetPath)}
          >
            Register dataset
          </button>
        </div>

        <label className="field lab-dataset-select">
          <span>Dataset snapshot</span>
          <select value={selected} onChange={(event) => setSelectedFingerprint(event.target.value)}>
            {datasets.length === 0 && <option value="">No datasets registered</option>}
            {datasets.map((dataset) => (
              <option key={dataset.dataset_fingerprint} value={dataset.dataset_fingerprint}>
                {dataset.name + " · " + dataset.case_count + " cases · " + dataset.dataset_fingerprint.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>

        <div className="lab-config-grid">
          <article className="lab-config-card">
            <span className="eyebrow">CONFIG A</span>
            <label className="field">
              <span>Retrieval mode</span>
              <select value={modeA} onChange={(event) => setModeA(event.target.value as RetrievalMode)}>
                {modes.map((mode) => <option key={mode}>{mode}</option>)}
              </select>
            </label>
            <label className="lab-check">
              <input type="checkbox" checked={rerankA} onChange={(event) => setRerankA(event.target.checked)} />
              deterministic rerank
            </label>
          </article>

          <article className="lab-config-card">
            <span className="eyebrow">CONFIG B</span>
            <label className="field">
              <span>Retrieval mode</span>
              <select value={modeB} onChange={(event) => setModeB(event.target.value as RetrievalMode)}>
                {modes.map((mode) => <option key={mode}>{mode}</option>)}
              </select>
            </label>
            <label className="lab-check">
              <input type="checkbox" checked={rerankB} onChange={(event) => setRerankB(event.target.checked)} />
              deterministic rerank
            </label>
          </article>

          <article className="lab-config-card lab-shared">
            <span className="eyebrow">SHARED</span>
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
            <button
              className="primary"
              disabled={busy || !workspaceReady || !selected}
              onClick={() => onRunAB(
                selected,
                makeConfig("A · " + modeA, modeA, rerankA),
                makeConfig("B · " + modeB, modeB, rerankB),
              )}
            >
              {busy ? "Running benchmark…" : "Run A/B benchmark"}
            </button>
          </article>
        </div>

        {comparison ? (
          <>
            <div className="lab-section-title">
              <div>
                <span className="eyebrow">OBJECTIVE METRICS</span>
                <h3>{comparison.dataset_name}</h3>
              </div>
              <div className="lab-run-actions">
                <button className="secondary" onClick={() => onExport(comparison.run_b.run_id, "json")}>Export JSON</button>
                <button className="secondary" onClick={() => onExport(comparison.run_b.run_id, "csv")}>Export CSV</button>
              </div>
            </div>

            <div className="metric-table">
              <div className="metric-head"><span>Metric</span><span>A</span><span>B</span><span>Δ B−A</span></div>
              {comparison.metrics.map((metric) => (
                <div className="metric-row" key={metric.metric}>
                  <strong>{metricLabel(metric.metric)}</strong>
                  <span>{metricValue(metric.a)}</span>
                  <span>{metricValue(metric.b)}</span>
                  <span className={metric.delta !== null && metric.delta !== 0 ? "metric-delta" : ""}>
                    {metric.delta === null ? "—" : (metric.delta >= 0 ? "+" : "") + metric.delta.toFixed(3)}
                  </span>
                </div>
              ))}
            </div>

            <div className="model-judged-note">
              <strong>Model-judged metrics</strong>
              <span>
                {comparison.model_judged_metrics.length === 0
                  ? "None configured. The table above contains deterministic objective metrics only."
                  : comparison.model_judged_metrics.length + " model-judged metrics"}
              </span>
            </div>

            <div className="lab-section-title">
              <div>
                <span className="eyebrow">FAILED CASES</span>
                <h3>{comparison.failed_cases.length + " need inspection"}</h3>
              </div>
            </div>
            <div className="lab-case-list">
              {comparison.failed_cases.length === 0 ? (
                <div className="empty">No failed cases in either configuration.</div>
              ) : comparison.failed_cases.map((item) => (
                <article className="lab-case" key={item.case_id}>
                  <div>
                    <strong>{item.case_id}</strong>
                    <p>{item.question}</p>
                  </div>
                  <div className="lab-case-states">
                    <span>{"A · " + (item.a_state ?? "ERROR") + " · " + (item.a_passed ? "pass" : "fail")}</span>
                    <span>{"B · " + (item.b_state ?? "ERROR") + " · " + (item.b_passed ? "pass" : "fail")}</span>
                  </div>
                  <div className="lab-case-actions">
                    {item.a_query_run_id && (
                      <button className="secondary" onClick={() => onInspectCase(comparison.run_a.run_id, item.case_id)}>
                        Trace A
                      </button>
                    )}
                    {item.b_query_run_id && (
                      <button className="secondary" onClick={() => onInspectCase(comparison.run_b.run_id, item.case_id)}>
                        Trace B
                      </button>
                    )}
                  </div>
                  <small>
                    {[...item.a_failures, ...item.b_failures]
                      .filter((value, index, all) => all.indexOf(value) === index)
                      .join(" · ")}
                  </small>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="empty lab-empty">
            Register a versioned dataset, choose two retrieval configurations, and run the same cases through both. Every failed case retains its Ask trace.
          </div>
        )}
      </section>

      <aside className="panel lab-sidebar">
        <span className="eyebrow">RUN HISTORY</span>
        <h2>Persisted benchmarks</h2>
        <div className="lab-run-list">
          {runs.length === 0 ? <div className="empty">No Lab runs yet.</div> : runs.slice(0, 12).map((run) => (
            <article key={run.run_id}>
              <div>
                <strong>{run.config.name}</strong>
                <span>{run.config.retrieval_mode}</span>
              </div>
              <code>{run.run_id.slice(0, 10)}</code>
              <small>
                {run.metrics
                  ? run.metrics.passed_cases + "/" + run.metrics.case_count + " passed · " + run.metrics.mean_latency_ms.toFixed(1) + " ms mean"
                  : run.status}
              </small>
            </article>
          ))}
        </div>
        <div className="lab-snapshot">
          <strong>Reproducibility</strong>
          <span>Dataset fingerprint</span>
          <span>Corpus fingerprint</span>
          <span>Provider identities</span>
          <span>RRF / candidate / rerank settings</span>
        </div>
        {exportPath && (
          <div className="lab-export-path">
            <span>Last export</span>
            <code>{exportPath}</code>
          </div>
        )}
      </aside>
    </div>
  );
}
