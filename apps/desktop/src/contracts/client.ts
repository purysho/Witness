import { invoke } from "@tauri-apps/api/core";
import {
  PROTOCOL_VERSION,
  type AskResult,
  type EvalConfigInput,
  type EvalDatasetSummary,
  type EvalRunSummary,
  type GraphSnapshot,
  type LabCaseDetail,
  type LabComparison,
  type LabRunResult,
  type RpcEnvelope,
  type RpcRequest,
  type SourceVersionSummary,
  type WorkspaceOpenResult,
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
  importSource: (path: string, validFrom?: string) =>
    call<Record<string, unknown>>("source.import", {
      path,
      ...(validFrom ? { valid_from: validFrom } : {}),
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

  labLoadDataset: (path: string) =>
    call<EvalDatasetSummary>("lab.dataset.load", { path }),
  labDatasets: () =>
    call<{ datasets: EvalDatasetSummary[] }>("lab.dataset.list"),
  labRun: (datasetFingerprint: string, config: EvalConfigInput) =>
    call<LabRunResult>("lab.run", {
      dataset_fingerprint: datasetFingerprint,
      config,
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
};
