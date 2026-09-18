import { invoke } from "@tauri-apps/api/core";
import {
  PROTOCOL_VERSION,
  type AskResult,
  type AttackManifestSummary,
  type AttackRunListItem,
  type AttackRunResult,
  type EvalConfigInput,
  type EvalDatasetSummary,
  type EvalRunSummary,
  type GraphSnapshot,
  type LabCaseDetail,
  type ProviderSnapshot,
  type LabComparison,
  type LabRunResult,
  type RpcEnvelope,
  type RpcRequest,
  type SourceVersionSummary,
  type VisualEvidencePreview,
  type WorkspaceHealthReport,
  type WorkspaceOpenResult,
  type WorkspaceRepairResult,
} from "../../../../contracts/generated/rpc";

let sequence = 0;

async function call<T>(
  method: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  sequence += 1;
  const request: RpcRequest = {
    v: PROTOCOL_VERSION,
    id: `ui_${Date.now()}_${sequence}`,
    method,
    params,
  };
  const response = await invoke<RpcEnvelope<T>>("engine_call", { request });
  if (response.type === "error") {
    throw new Error(`${response.error.code}: ${response.error.message}`);
  }
  return response.result;
}

export const engine = {
  ping: () => call<{ ok: boolean; protocol_version: number }>("ping"),
  openWorkspace: (path: string) =>
    call<WorkspaceOpenResult>("workspace.open", { path }),
  workspaceHealth: () =>
    call<WorkspaceHealthReport>("workspace.health"),
  repairWorkspace: () =>
    call<WorkspaceRepairResult>("workspace.repair"),
  providerSettings: () =>
    call<ProviderSnapshot>("providers.get"),
  setProviderSettings: (
    embeddingDimensions: number,
    visualMode: "off" | "hash",
    visualDimensions: number,
  ) =>
    call<ProviderSnapshot>("providers.set", {
      embedding_dimensions: embeddingDimensions,
      visual_mode: visualMode,
      visual_dimensions: visualDimensions,
    }),
  importSource: (path: string, validFrom?: string, jobId?: string) =>
    call<Record<string, unknown>>("source.import", {
      path,
      ...(validFrom ? { valid_from: validFrom } : {}),
      ...(jobId ? { job_id: jobId } : {}),
    }),
  listSources: () =>
    call<{ sources: SourceVersionSummary[] }>("source.list"),
  ask: (question: string, limit = 10) =>
    call<AskResult>("query.run", { question, limit }),
  trace: (runId: string) =>
    call<{ run_id: string; events: AskResult["trace"]; answer: AskResult["answer"] }>(
      "query.trace",
      { run_id: runId },
    ),
  graph: (limit = 160) =>
    call<GraphSnapshot>("graph.snapshot", { limit }),
  visualEvidence: (visualEvidenceId: string) =>
    call<VisualEvidencePreview>("visual.evidence.get", {
      visual_evidence_id: visualEvidenceId,
    }),
  cancelJob: (workspacePath: string, jobId: string) =>
    invoke<void>("cancel_job", {
      workspacePath,
      jobId,
    }),

  labLoadDataset: (path: string) =>
    call<EvalDatasetSummary>("lab.dataset.load", { path }),
  labDatasets: () =>
    call<{ datasets: EvalDatasetSummary[] }>("lab.dataset.list"),
  labRun: (
    datasetFingerprint: string,
    config: EvalConfigInput,
    jobId?: string,
  ) =>
    call<LabRunResult>("lab.run", {
      dataset_fingerprint: datasetFingerprint,
      config,
      ...(jobId ? { job_id: jobId } : {}),
    }),
  labRuns: (limit = 50) =>
    call<{ runs: EvalRunSummary[] }>("lab.runs", { limit }),
  labRunGet: (runId: string) =>
    call<LabRunResult>("lab.run.get", { run_id: runId }),
  labCase: (runId: string, caseId: string) =>
    call<LabCaseDetail>("lab.case", { run_id: runId, case_id: caseId }),
  labCompare: (runA: string, runB: string) =>
    call<LabComparison>("lab.compare", { run_a: runA, run_b: runB }),
  labExport: (runId: string, format: "json" | "csv", path?: string) =>
    call<{ path: string; format: string }>("lab.export", {
      run_id: runId,
      format,
      ...(path ? { path } : {}),
    }),

  attackLoadManifest: (path: string) =>
    call<AttackManifestSummary>("attack.manifest.load", { path }),
  attackManifests: () =>
    call<{ manifests: AttackManifestSummary[] }>("attack.manifest.list"),
  attackRun: (
    manifestFingerprint: string,
    datasetFingerprint: string,
    config: EvalConfigInput,
    jobId?: string,
  ) =>
    call<AttackRunResult>("attack.run", {
      manifest_fingerprint: manifestFingerprint,
      dataset_fingerprint: datasetFingerprint,
      config,
      ...(jobId ? { job_id: jobId } : {}),
    }),
  attackRuns: (limit = 50) =>
    call<{ runs: AttackRunListItem[] }>("attack.runs", { limit }),
  attackRunGet: (attackRunId: string) =>
    call<AttackRunResult>("attack.run.get", {
      attack_run_id: attackRunId,
    }),
  attackExport: (
    attackRunId: string,
    format: "json" | "csv",
    path?: string,
  ) =>
    call<{ path: string; format: string }>("attack.export", {
      attack_run_id: attackRunId,
      format,
      ...(path ? { path } : {}),
    }),
};
