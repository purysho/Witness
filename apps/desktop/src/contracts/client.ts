import { invoke } from "@tauri-apps/api/core";
import {
  PROTOCOL_VERSION,
  type AskResult,
  type GraphSnapshot,
  type RpcEnvelope,
  type RpcRequest,
  type SourceVersionSummary,
  type WorkspaceOpenResult,
} from "../../../../contracts/generated/rpc";

let sequence = 0;

async function call<T>(method:string, params:Record<string,unknown> = {}):Promise<T> {
  sequence += 1;
  const request:RpcRequest = {v:PROTOCOL_VERSION,id:`ui_${Date.now()}_${sequence}`,method,params};
  const response = await invoke<RpcEnvelope<T>>("engine_call",{request});
  if (response.type === "error") throw new Error(`${response.error.code}: ${response.error.message}`);
  return response.result;
}

export const engine = {
  ping:()=>call<{ok:boolean;protocol_version:number}>("ping"),
  openWorkspace:(path:string)=>call<WorkspaceOpenResult>("workspace.open",{path}),
  importSource:(path:string,validFrom?:string)=>call<Record<string,unknown>>("source.import",{path,...(validFrom?{valid_from:validFrom}:{})}),
  listSources:()=>call<{sources:SourceVersionSummary[]}>("source.list"),
  ask:(question:string,limit=10)=>call<AskResult>("query.run",{question,limit}),
  trace:(runId:string)=>call<{run_id:string;events:AskResult["trace"];answer:AskResult["answer"]}>("query.trace",{run_id:runId}),
  graph:(limit=160)=>call<GraphSnapshot>("graph.snapshot",{limit}),
};
