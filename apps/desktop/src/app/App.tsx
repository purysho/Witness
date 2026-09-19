import { useEffect, useState } from "react";
import {
  open as openDialog,
  save as saveDialog,
} from "@tauri-apps/plugin-dialog";
import type {
  AskResult,
  AttackManifestSummary,
  AttackRunListItem,
  AttackRunResult,
  EvalConfigInput,
  EvalDatasetSummary,
  EvalRunSummary,
  GraphSnapshot,
  LabComparison,
  ProviderSnapshot,
  SourceVersionDetail,
  SourceVersionSummary,
  VisualEvidencePreview,
  WorkspaceHealthReport,
  WorkspaceOpenResult,
} from "../../../../contracts/generated/rpc";
import { engine } from "../contracts/client";
import { AskView } from "../features/ask/AskView";
import { AttackView } from "../features/attack/AttackView";
import { GraphView } from "../features/graph/GraphView";
import { LabView } from "../features/lab/LabView";
import { LibraryPanel } from "../features/library/LibraryPanel";
import { ProviderPanel } from "../features/providers/ProviderPanel";
import { TraceView } from "../features/trace/TraceView";
import { VisualEvidenceViewer } from "../features/visual/VisualEvidenceViewer";

type Tab = "ask" | "trace" | "graph" | "lab" | "attack";

const LAST_WORKSPACE_KEY = "witness:last-workspace";

function rememberedWorkspace(): string {
  try {
    return window.localStorage.getItem(LAST_WORKSPACE_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberWorkspace(path: string) {
  try {
    window.localStorage.setItem(LAST_WORKSPACE_KEY, path);
  } catch {
    // A remembered path is a convenience only; workspace state stays canonical
    // in the engine and must not depend on browser storage.
  }
}

function createJobId(kind: string): string {
  const suffix =
    globalThis.crypto?.randomUUID?.() ??
    Math.random().toString(36).slice(2);
  return kind + "-" + Date.now() + "-" + suffix;
}

function isCancellation(reason: unknown): boolean {
  const message = String(reason).toLocaleLowerCase();
  return message.includes("cancelled") || message.includes("canceled");
}

export function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [rememberedAtLaunch] = useState(() => rememberedWorkspace());
  const [workspacePath, setWorkspacePath] = useState(rememberedAtLaunch);
  const [workspace, setWorkspace] = useState<WorkspaceOpenResult | null>(null);
  const [workspaceHealth, setWorkspaceHealth] =
    useState<WorkspaceHealthReport | null>(null);
  const [providers, setProviders] = useState<ProviderSnapshot | null>(null);
  const [sourcePath, setSourcePath] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [sources, setSources] = useState<SourceVersionSummary[]>([]);
  const [selectedSource, setSelectedSource] = useState<SourceVersionDetail | null>(null);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [labDatasets, setLabDatasets] = useState<EvalDatasetSummary[]>([]);
  const [labRuns, setLabRuns] = useState<EvalRunSummary[]>([]);
  const [labComparison, setLabComparison] = useState<LabComparison | null>(null);
  const [labExportPath, setLabExportPath] = useState<string | null>(null);
  const [attackManifests, setAttackManifests] = useState<AttackManifestSummary[]>([]);
  const [attackRuns, setAttackRuns] = useState<AttackRunListItem[]>([]);
  const [attackResult, setAttackResult] = useState<AttackRunResult | null>(null);
  const [visualPreview, setVisualPreview] = useState<VisualEvidencePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeJob, setActiveJob] =
    useState<{ id: string; label: string } | null>(null);
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

  async function refreshWorkspaceHealth() {
    const report = await engine.workspaceHealth();
    setWorkspaceHealth(report);
    return report;
  }

  async function refreshProviders() {
    const snapshot = await engine.providerSettings();
    setProviders(snapshot);
    return snapshot;
  }


  async function refreshLab() {
    const [datasets, runs] = await Promise.all([
      engine.labDatasets(),
      engine.labRuns(),
    ]);
    setLabDatasets(datasets.datasets);
    setLabRuns(runs.runs);
  }

  async function refreshAttack() {
    const [manifests, runs] = await Promise.all([
      engine.attackManifests(),
      engine.attackRuns(),
    ]);
    setAttackManifests(manifests.manifests);
    setAttackRuns(runs.runs);
  }

  async function openWorkspacePath(path: string) {
    const normalized = path.trim();
    if (!normalized) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const opened = await engine.openWorkspace(normalized);
      setWorkspacePath(opened.path);
      rememberWorkspace(opened.path);
      setWorkspace(opened);
      setWorkspaceHealth(null);
      setProviders(null);
      setSelectedSource(null);
      setResult(null);
      setGraph(null);
      setLabComparison(null);
      setLabExportPath(null);
      setAttackResult(null);
      setVisualPreview(null);
      const [, , , health] = await Promise.all([
        refreshSources(),
        refreshLab(),
        refreshAttack(),
        refreshWorkspaceHealth(),
        refreshProviders(),
      ]);
      setStatus(
        "Workspace open · " +
          opened.embedding_provider_id +
          " · health " +
          health.status,
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function openWorkspace() {
    await openWorkspacePath(workspacePath);
  }

  async function browseWorkspace() {
    setError(null);
    try {
      const selected = await openDialog({
        directory: true,
        multiple: false,
        title: "Choose a Witness workspace folder",
      });
      if (typeof selected === "string") {
        setWorkspacePath(selected);
        await openWorkspacePath(selected);
      }
    } catch (reason) {
      setError("Could not open workspace picker: " + String(reason));
    }
  }

  async function backupWorkspace() {
    if (!workspace) {
      return;
    }
    setError(null);
    try {
      const stamp = new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[T:]/g, "-");
      const selected = await saveDialog({
        title: "Back up Witness workspace",
        defaultPath: workspace.path + "-" + stamp + ".witness-backup",
        filters: [
          {
            name: "Witness workspace backup",
            extensions: ["witness-backup"],
          },
        ],
      });
      if (typeof selected !== "string") {
        return;
      }
      setBusy(true);
      const backup = await engine.backupWorkspace(selected);
      setStatus(
        "Workspace backup created · " +
          backup.protected_state_fingerprint.slice(0, 12) +
          " · " +
          backup.path,
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function restoreWorkspaceBackup() {
    setError(null);
    try {
      const backupPath = await openDialog({
        directory: false,
        multiple: false,
        title: "Choose a Witness workspace backup",
        filters: [
          {
            name: "Witness workspace backup",
            extensions: ["witness-backup"],
          },
        ],
      });
      if (typeof backupPath !== "string") {
        return;
      }

      const destinationPath = await openDialog({
        directory: true,
        multiple: false,
        title: "Choose an empty folder for the restored workspace",
      });
      if (typeof destinationPath !== "string") {
        return;
      }

      setBusy(true);
      const restored = await engine.restoreWorkspace(
        backupPath,
        destinationPath,
      );
      setStatus(
        "Backup verified · restored fingerprint " +
          restored.protected_state_fingerprint.slice(0, 12),
      );
      await openWorkspacePath(restored.path);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function loadFirstRunDemo() {
    setBusy(true);
    setError(null);
    try {
      const demo = await engine.loadDemo();
      const [sourceState, , , health, providerState] = await Promise.all([
        engine.listSources(),
        refreshLab(),
        refreshAttack(),
        refreshWorkspaceHealth(),
        refreshProviders(),
      ]);
      setSources(sourceState.sources);
      setProviders(providerState);
      setQuestion(demo.suggested_question);
      const response = await engine.ask(demo.suggested_question);
      setResult(response);
      setTab("trace");
      setStatus(
        "Demo ready · " +
          demo.dataset.name +
          " · Trace opened · " +
          response.answer.state,
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  function scrollToLibrary() {
    document.getElementById("library")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  async function browseSource() {
    setError(null);
    try {
      const selected = await openDialog({
        directory: false,
        multiple: false,
        title: "Choose an evidence source",
        filters: [
          {
            name: "Evidence files",
            extensions: [
              "pdf", "md", "markdown", "txt", "html", "htm",
              "docx", "pptx", "xlsx", "csv", "json", "py", "js",
              "ts", "tsx", "jsx", "rs", "go", "java", "c", "cpp",
              "h", "hpp", "toml", "yaml", "yml",
            ],
          },
        ],
      });
      if (typeof selected === "string") {
        setSourcePath(selected);
      }
    } catch (reason) {
      setError("Could not open source picker: " + String(reason));
    }
  }

  async function importSource() {
    const jobId = createJobId("import");
    setBusy(true);
    setActiveJob({ id: jobId, label: "source import" });
    setError(null);
    try {
      await engine.importSource(
        sourcePath,
        validFrom || undefined,
        jobId,
      );
      await Promise.all([
        refreshSources(),
        refreshWorkspaceHealth(),
        refreshProviders(),
      ]);
      setSourcePath("");
      setSelectedSource(null);
      setStatus(
        "Source indexed into lexical, dense, temporal, hierarchy, graph, and visual projections.",
      );
    } catch (reason) {
      if (isCancellation(reason)) {
        await Promise.all([refreshSources(), refreshWorkspaceHealth()]);
        setStatus("Source import cancelled · partial new-version state rolled back.");
      } else {
        setError(String(reason));
      }
    } finally {
      setActiveJob((current) => current?.id === jobId ? null : current);
      setBusy(false);
    }
  }

  async function inspectSource(sourceVersionId: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await engine.sourceDetail(sourceVersionId);
      setSelectedSource(detail);
      setStatus(
        "Source detail loaded · " +
          detail.version_chain.length +
          " version" +
          (detail.version_chain.length === 1 ? "" : "s") +
          " in chain",
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function archiveSource(sourceVersionId: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await engine.archiveSource(sourceVersionId);
      await refreshSources();
      setSelectedSource(detail);
      setGraph(null);
      setStatus(
        "Source archived · canonical evidence and prior Trace history retained.",
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function restoreSource(sourceVersionId: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await engine.restoreSource(sourceVersionId);
      await refreshSources();
      setSelectedSource(detail);
      setGraph(null);
      setStatus("Source restored · retrieval eligibility recalculated.");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function repairWorkspaceIndexes() {
    setBusy(true);
    setError(null);
    try {
      const repaired = await engine.repairWorkspace();
      setWorkspaceHealth(repaired.after);
      await refreshProviders();
      setStatus(
        repaired.actions.length
          ? "Workspace repaired · " + repaired.actions.join(" · ")
          : "Workspace checked · no repairable projections needed",
      );
      if (!repaired.protected_state_unchanged) {
        throw new Error(
          "Repair changed protected workspace state; this should never occur.",
        );
      }
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function applyProviderSettings(
    embeddingMode: "hash" | "sentence-transformers",
    embeddingModel: string,
    embeddingDimensions: number,
    visualMode: "off" | "hash",
    visualDimensions: number,
  ) {
    setBusy(true);
    setError(null);
    try {
      const snapshot = await engine.setProviderSettings(
        embeddingMode,
        embeddingModel,
        embeddingDimensions,
        visualMode,
        visualDimensions,
      );
      setProviders(snapshot);
      const health = await refreshWorkspaceHealth();
      const needsRepair =
        snapshot.embedding.reindex_required ||
        snapshot.visual.reindex_required;
      setStatus(
        needsRepair
          ? "Provider settings applied · derived indexes need repair"
          : "Provider settings applied · indexes current · health " + health.status,
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
    const jobA = createJobId("lab-a");
    let activeId = jobA;
    setBusy(true);
    setActiveJob({ id: jobA, label: "Lab run A" });
    setError(null);
    setLabExportPath(null);
    try {
      const runA = await engine.labRun(
        datasetFingerprint,
        configA,
        jobA,
      );
      const jobB = createJobId("lab-b");
      activeId = jobB;
      setActiveJob({ id: jobB, label: "Lab run B" });
      const runB = await engine.labRun(
        datasetFingerprint,
        configB,
        jobB,
      );
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
      if (isCancellation(reason)) {
        await refreshLab();
        setStatus("Lab run cancelled · completed case results were preserved.");
      } else {
        setError(String(reason));
      }
    } finally {
      setActiveJob((current) => current?.id === activeId ? null : current);
      setBusy(false);
    }
  }

  async function compareLabRuns(runA: string, runB: string) {
    setBusy(true);
    setError(null);
    setLabExportPath(null);
    try {
      const comparison = await engine.labCompare(runA, runB);
      setLabComparison(comparison);
      setStatus(
        "Loaded persisted Lab comparison · " +
          comparison.run_a.config.name +
          " vs " +
          comparison.run_b.config.name,
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

  async function loadAttackManifest(path: string) {
    setBusy(true);
    setError(null);
    try {
      const manifest = await engine.attackLoadManifest(path);
      await refreshAttack();
      setStatus(
        "Attack manifest registered · " +
          manifest.name +
          " · " +
          manifest.mutation_count +
          " mutations",
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function runAttack(
    manifestFingerprint: string,
    datasetFingerprint: string,
    config: EvalConfigInput,
  ) {
    const jobId = createJobId("attack");
    setBusy(true);
    setActiveJob({ id: jobId, label: "Attack Lab run" });
    setError(null);
    try {
      const result = await engine.attackRun(
        manifestFingerprint,
        datasetFingerprint,
        config,
        jobId,
      );
      setAttackResult(result);
      await Promise.all([refreshAttack(), refreshLab()]);
      const failed = result.invariants.filter((item) => item.status === "FAIL").length;
      setStatus(
        "Attack run complete · " +
          result.run.attack_name +
          " · " +
          failed +
          " invariant failures",
      );
    } catch (reason) {
      if (isCancellation(reason)) {
        await Promise.all([refreshAttack(), refreshLab()]);
        setStatus("Attack Lab run cancelled · canonical corpus remains isolated.");
      } else {
        setError(String(reason));
      }
    } finally {
      setActiveJob((current) => current?.id === jobId ? null : current);
      setBusy(false);
    }
  }

  async function exportAttack(
    attackRunId: string,
    format: "json" | "csv",
  ) {
    setBusy(true);
    setError(null);
    try {
      const exported = await engine.attackExport(attackRunId, format);
      setStatus("Attack export written · " + exported.path);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function loadAttackRun(attackRunId: string) {
    setBusy(true);
    setError(null);
    try {
      setAttackResult(await engine.attackRunGet(attackRunId));
      setStatus("Loaded persisted Attack Lab run · " + attackRunId.slice(0, 10));
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  function inspectAttackCase(
    side: "clean" | "attacked",
    caseId: string,
  ) {
    const caseResult = attackResult?.[side].cases.find(
      (item) => item.case_id === caseId,
    );
    if (!caseResult?.ask_result) {
      setError("This attack case has no completed Ask trace.");
      return;
    }
    setResult(caseResult.ask_result);
    setTab("trace");
    setStatus(
      "Opened " + side + " attack trace · " + caseId,
    );
  }

  async function cancelActiveJob() {
    if (!workspace || !activeJob) {
      return;
    }
    setError(null);
    try {
      await engine.cancelJob(workspace.path, activeJob.id);
      setStatus("Cancellation requested · " + activeJob.label);
    } catch (reason) {
      setError("Could not request cancellation: " + String(reason));
    }
  }

  async function openVisualEvidence(visualEvidenceId: string) {
    setBusy(true);
    setError(null);
    try {
      setVisualPreview(await engine.visualEvidence(visualEvidenceId));
      setStatus("Opened visual evidence · " + visualEvidenceId.slice(0, 10));
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
    if (tab === "attack" && workspace && !busy) {
      void refreshAttack();
    }
  }, [tab, workspace]);

  const nav: Array<{ tab: Tab; number: string }> = [
    { tab: "ask", number: "01" },
    { tab: "trace", number: "02" },
    { tab: "graph", number: "03" },
    { tab: "lab", number: "04" },
    { tab: "attack", number: "05" },
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
          <div className="workspace-actions">
            <button
              className="secondary"
              disabled={busy}
              onClick={browseWorkspace}
            >
              Choose folder
            </button>
            <button
              className="secondary"
              disabled={busy || !workspacePath.trim()}
              onClick={openWorkspace}
            >
              {workspace ? "Reopen" : "Open / create path"}
            </button>
          </div>
          {activeJob && (
            <button
              className="cancel-job"
              onClick={cancelActiveJob}
            >
              Cancel {activeJob.label}
            </button>
          )}
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

        {!workspace && (
          <section className="panel first-run-panel">
            <div>
              <span className="eyebrow">FIRST RUN</span>
              <h2>Start with a local evidence workspace</h2>
              <p>
                Choose an existing folder, or type a new folder path in the
                Workspace field above and select Open / create path. Witness
                creates a missing folder and keeps all evidence data local.
              </p>
              <small className="first-run-note">
                No account, cloud sync, Python install, or server setup is required.
              </small>
            </div>
            <ol className="first-run-steps">
              <li><strong>01</strong><span>Open or create a local workspace.</span></li>
              <li><strong>02</strong><span>Try the demo or import your own evidence.</span></li>
              <li><strong>03</strong><span>Ask a question, then inspect its Trace.</span></li>
            </ol>
            <div className="first-run-actions">
              {workspacePath.trim() && (
                <button
                  className="primary"
                  disabled={busy}
                  onClick={openWorkspace}
                >
                  {rememberedAtLaunch &&
                  workspacePath.trim() === rememberedAtLaunch
                    ? "Continue last workspace"
                    : "Open / create entered path"}
                </button>
              )}
              <button
                className={workspacePath.trim() ? "secondary" : "primary"}
                disabled={busy}
                onClick={browseWorkspace}
              >
                {workspacePath.trim() ? "Choose another folder" : "Choose folder"}
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={restoreWorkspaceBackup}
              >
                Restore backup
              </button>
            </div>
          </section>
        )}

        {workspace && workspaceHealth && (
          <section
            className={
              "workspace-health-panel health-" + workspaceHealth.status
            }
          >
            <div>
              <span>WORKSPACE HEALTH</span>
              <strong>{workspaceHealth.status.toUpperCase()}</strong>
              <small>
                {workspaceHealth.issues.length === 0
                  ? "Canonical evidence and derived projections are consistent."
                  : workspaceHealth.issues[0].detail}
              </small>
            </div>
            <div className="workspace-health-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={backupWorkspace}
              >
                Backup workspace
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={restoreWorkspaceBackup}
              >
                Restore backup
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void refreshWorkspaceHealth()}
              >
                Recheck
              </button>
              {workspaceHealth.issues.some((item) => item.repairable) && (
                <button
                  className="primary"
                  disabled={busy}
                  onClick={repairWorkspaceIndexes}
                >
                  Repair derived indexes
                </button>
              )}
            </div>
          </section>
        )}

        {workspace && sources.length === 0 && (
          <section className="demo-onboarding">
            <div>
              <span className="eyebrow">EMPTY WORKSPACE</span>
              <strong>Try Witness with the demo, or start with your own evidence.</strong>
              <small>
                The demo installs a small local versioned evidence pack, runs a
                real question, and opens its Trace. Nothing is downloaded from a
                model provider.
              </small>
            </div>
            <div className="demo-onboarding-actions">
              <button
                className="primary"
                disabled={busy}
                onClick={loadFirstRunDemo}
              >
                Try demo & open Trace
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={scrollToLibrary}
              >
                Import my own files
              </button>
            </div>
          </section>
        )}

        {workspace && providers && (
          <ProviderPanel
            snapshot={providers}
            busy={busy}
            onApply={applyProviderSettings}
          />
        )}

        <LibraryPanel
          sourcePath={sourcePath}
          validFrom={validFrom}
          sources={sources}
          selectedSource={selectedSource}
          busy={busy}
          workspaceReady={Boolean(workspace)}
          onSourcePath={setSourcePath}
          onValidFrom={setValidFrom}
          onBrowseSource={browseSource}
          onImport={importSource}
          onInspectSource={inspectSource}
          onArchiveSource={archiveSource}
          onRestoreSource={restoreSource}
          onClearSourceDetails={() => setSelectedSource(null)}
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
              onOpenVisual={openVisualEvidence}
            />
          )}
          {tab === "trace" && (
            <TraceView
              result={result}
              onOpenVisual={openVisualEvidence}
            />
          )}
          {tab === "graph" && (
            <GraphView
              graph={graph}
              onRefresh={refreshGraph}
              busy={busy}
            />
          )}
          {tab === "attack" && (
            <AttackView
              workspaceReady={Boolean(workspace)}
              busy={busy}
              datasets={labDatasets}
              manifests={attackManifests}
              runs={attackRuns}
              result={attackResult}
              onLoadManifest={loadAttackManifest}
              onRun={runAttack}
              onLoadRun={loadAttackRun}
              onInspectCase={inspectAttackCase}
              onExport={exportAttack}
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
              onCompareRuns={compareLabRuns}
              onExport={exportLab}
            />
          )}
        </section>
      </div>
      {visualPreview && (
        <VisualEvidenceViewer
          preview={visualPreview}
          onClose={() => setVisualPreview(null)}
        />
      )}
    </main>
  );
}
