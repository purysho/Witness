import { useEffect, useState } from "react";
import type {
  AskResult,
  EvalConfigInput,
  EvalDatasetSummary,
  EvalRunSummary,
  GraphSnapshot,
  LabComparison,
  SourceVersionSummary,
  WorkspaceOpenResult,
} from "../../../../contracts/generated/rpc";
import { engine } from "../contracts/client";
import { AskView } from "../features/ask/AskView";
import { GraphView } from "../features/graph/GraphView";
import { LabView } from "../features/lab/LabView";
import { LibraryPanel } from "../features/library/LibraryPanel";
import { TraceView } from "../features/trace/TraceView";

type Tab = "ask" | "trace" | "graph" | "lab";

export function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [workspacePath, setWorkspacePath] = useState("");
  const [workspace, setWorkspace] = useState<WorkspaceOpenResult | null>(null);
  const [sourcePath, setSourcePath] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [sources, setSources] = useState<SourceVersionSummary[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [labDatasets, setLabDatasets] = useState<EvalDatasetSummary[]>([]);
  const [labRuns, setLabRuns] = useState<EvalRunSummary[]>([]);
  const [labComparison, setLabComparison] = useState<LabComparison | null>(null);
  const [labExportPath, setLabExportPath] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Engine not contacted yet.");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    engine
      .ping()
      .then(() => setStatus("Engine ready · local NDJSON IPC"))
      .catch((reason) => setStatus("Engine unavailable: " + String(reason)));
  }, []);

  async function refreshSources() {
    setSources((await engine.listSources()).sources);
  }

  async function refreshLab() {
    const [datasets, runs] = await Promise.all([
      engine.labDatasets(),
      engine.labRuns(),
    ]);
    setLabDatasets(datasets.datasets);
    setLabRuns(runs.runs);
  }

  async function openWorkspace() {
    setBusy(true);
    setError(null);
    try {
      const opened = await engine.openWorkspace(workspacePath);
      setWorkspace(opened);
      setResult(null);
      setGraph(null);
      setLabComparison(null);
      setLabExportPath(null);
      await Promise.all([refreshSources(), refreshLab()]);
      setStatus("Workspace open · " + opened.embedding_provider_id);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function importSource() {
    setBusy(true);
    setError(null);
    try {
      await engine.importSource(sourcePath, validFrom || undefined);
      await refreshSources();
      setSourcePath("");
      setStatus(
        "Source indexed into lexical, dense, temporal, hierarchy, and graph projections.",
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function ask() {
    setBusy(true);
    setError(null);
    try {
      const response = await engine.ask(question);
      setResult(response);
      setStatus("Run complete · " + response.answer.state);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function refreshGraph() {
    setBusy(true);
    setError(null);
    try {
      setGraph(await engine.graph());
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function loadLabDataset(path: string) {
    setBusy(true);
    setError(null);
    try {
      const dataset = await engine.labLoadDataset(path);
      await refreshLab();
      setStatus(
        "Lab dataset registered · " +
          dataset.name +
          " · " +
          dataset.case_count +
          " cases",
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function runLabAB(
    datasetFingerprint: string,
    configA: EvalConfigInput,
    configB: EvalConfigInput,
  ) {
    setBusy(true);
    setError(null);
    setLabExportPath(null);
    try {
      const runA = await engine.labRun(datasetFingerprint, configA);
      const runB = await engine.labRun(datasetFingerprint, configB);
      const comparison = await engine.labCompare(
        runA.run.run_id,
        runB.run.run_id,
      );
      setLabComparison(comparison);
      await refreshLab();
      setStatus(
        "Lab comparison complete · " +
          comparison.run_a.config.retrieval_mode +
          " vs " +
          comparison.run_b.config.retrieval_mode,
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function inspectLabCase(runId: string, caseId: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await engine.labCase(runId, caseId);
      if (!detail.ask_result) {
        throw new Error("This Lab case has no completed Ask trace.");
      }
      setResult(detail.ask_result);
      setTab("trace");
      setStatus("Opened Lab case trace · " + caseId);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function exportLab(runId: string, format: "json" | "csv") {
    setBusy(true);
    setError(null);
    try {
      const exported = await engine.labExport(runId, format);
      setLabExportPath(exported.path);
      setStatus("Lab export written · " + exported.path);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (tab === "graph" && workspace && !graph && !busy) {
      void refreshGraph();
    }
    if (tab === "lab" && workspace && !busy) {
      void refreshLab();
    }
  }, [tab, workspace]);

  const nav: Array<{ tab: Tab; number: string }> = [
    { tab: "ask", number: "01" },
    { tab: "trace", number: "02" },
    { tab: "graph", number: "03" },
    { tab: "lab", number: "04" },
  ];

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="witness-mark" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
            <b />
          </div>
          <div>
            <strong>WITNESS</strong>
            <span>evidence workbench</span>
          </div>
        </div>

        <nav>
          {nav.map((item) => (
            <button
              className={tab === item.tab ? "active" : ""}
              key={item.tab}
              onClick={() => setTab(item.tab)}
            >
              <span>{item.number}</span>
              {item.tab}
            </button>
          ))}
        </nav>

        <div className="sidebar-note">
          <span>Evidence state</span>
          <strong>{result?.answer.state ?? "NO RUN"}</strong>
          <small>
            Structured artifacts only. No hidden reasoning is exposed.
          </small>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <label className="workspace-field">
            <span>WORKSPACE</span>
            <input
              value={workspacePath}
              onChange={(event) => setWorkspacePath(event.target.value)}
              placeholder="C:\Witness\Research.witness"
            />
          </label>
          <button
            className="secondary"
            disabled={busy || !workspacePath.trim()}
            onClick={openWorkspace}
          >
            {workspace ? "Reopen" : "Open workspace"}
          </button>
          <div className="engine-status">
            <span className={workspace ? "status-dot ready" : "status-dot"} />
            <div>
              <strong>
                {workspace ? "LOCAL WORKSPACE" : "NO WORKSPACE"}
              </strong>
              <small>{status}</small>
            </div>
          </div>
        </header>

        {error && (
          <div className="error-banner">
            <strong>Request failed</strong>
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        <LibraryPanel
          sourcePath={sourcePath}
          validFrom={validFrom}
          sources={sources}
          busy={busy}
          onSourcePath={setSourcePath}
          onValidFrom={setValidFrom}
          onImport={importSource}
        />

        <section className="surface">
          {tab === "ask" && (
            <AskView
              question={question}
              result={result}
              busy={busy}
              workspaceReady={Boolean(workspace)}
              onQuestion={setQuestion}
              onAsk={ask}
              onOpenTrace={() => setTab("trace")}
            />
          )}
          {tab === "trace" && <TraceView result={result} />}
          {tab === "graph" && (
            <GraphView
              graph={graph}
              onRefresh={refreshGraph}
              busy={busy}
            />
          )}
          {tab === "lab" && (
            <LabView
              workspaceReady={Boolean(workspace)}
              busy={busy}
              datasets={labDatasets}
              runs={labRuns}
              comparison={labComparison}
              exportPath={labExportPath}
              onLoadDataset={loadLabDataset}
              onRunAB={runLabAB}
              onInspectCase={inspectLabCase}
              onExport={exportLab}
            />
          )}
        </section>
      </div>
    </main>
  );
}
