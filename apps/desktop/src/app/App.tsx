import { useEffect, useState } from "react";
import type { AskResult, GraphSnapshot, SourceVersionSummary, WorkspaceOpenResult } from "../../../../contracts/generated/rpc";
import { engine } from "../contracts/client";
import { AskView } from "../features/ask/AskView";
import { GraphView } from "../features/graph/GraphView";
import { LibraryPanel } from "../features/library/LibraryPanel";
import { TraceView } from "../features/trace/TraceView";

type Tab="ask"|"trace"|"graph";

export function App() {
  const [tab,setTab]=useState<Tab>("ask");
  const [workspacePath,setWorkspacePath]=useState("");
  const [workspace,setWorkspace]=useState<WorkspaceOpenResult|null>(null);
  const [sourcePath,setSourcePath]=useState("");
  const [validFrom,setValidFrom]=useState("");
  const [sources,setSources]=useState<SourceVersionSummary[]>([]);
  const [question,setQuestion]=useState("");
  const [result,setResult]=useState<AskResult|null>(null);
  const [graph,setGraph]=useState<GraphSnapshot|null>(null);
  const [busy,setBusy]=useState(false);
  const [status,setStatus]=useState("Engine not contacted yet.");
  const [error,setError]=useState<string|null>(null);

  useEffect(()=>{engine.ping().then(()=>setStatus("Engine ready · local NDJSON IPC")).catch(reason=>setStatus(`Engine unavailable: ${String(reason)}`));},[]);
  async function refreshSources(){setSources((await engine.listSources()).sources);}
  async function openWorkspace(){
    setBusy(true);setError(null);
    try {const opened=await engine.openWorkspace(workspacePath);setWorkspace(opened);setResult(null);setGraph(null);await refreshSources();setStatus(`Workspace open · ${opened.embedding_provider_id}`);}
    catch(reason){setError(String(reason));} finally{setBusy(false);}
  }
  async function importSource(){
    setBusy(true);setError(null);
    try {await engine.importSource(sourcePath,validFrom||undefined);await refreshSources();setSourcePath("");setStatus("Source indexed into lexical, dense, temporal, hierarchy, and graph projections.");}
    catch(reason){setError(String(reason));} finally{setBusy(false);}
  }
  async function ask(){
    setBusy(true);setError(null);
    try {const response=await engine.ask(question);setResult(response);setStatus(`Run complete · ${response.answer.state}`);}
    catch(reason){setError(String(reason));} finally{setBusy(false);}
  }
  async function refreshGraph(){
    setBusy(true);setError(null);
    try {setGraph(await engine.graph());} catch(reason){setError(String(reason));} finally{setBusy(false);}
  }
  useEffect(()=>{if(tab==="graph"&&workspace&&!graph&&!busy) void refreshGraph();},[tab,workspace]);

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="witness-mark" aria-hidden="true"><i/><i/><i/><i/><b/></div><div><strong>WITNESS</strong><span>evidence workbench</span></div></div>
      <nav>{(["ask","trace","graph"] as const).map(item=>(
        <button className={tab===item?"active":""} key={item} onClick={()=>setTab(item)}>
          <span>{item==="ask"?"01":item==="trace"?"02":"03"}</span>{item}
        </button>
      ))}</nav>
      <div className="sidebar-note"><span>Evidence state</span><strong>{result?.answer.state??"NO RUN"}</strong><small>Structured artifacts only. No hidden reasoning is exposed.</small></div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        <label className="workspace-field"><span>WORKSPACE</span><input value={workspacePath} onChange={e=>setWorkspacePath(e.target.value)} placeholder="C:\Witness\Research.witness"/></label>
        <button className="secondary" disabled={busy||!workspacePath.trim()} onClick={openWorkspace}>{workspace?"Reopen":"Open workspace"}</button>
        <div className="engine-status"><span className={workspace?"status-dot ready":"status-dot"}/><div><strong>{workspace?"LOCAL WORKSPACE":"NO WORKSPACE"}</strong><small>{status}</small></div></div>
      </header>
      {error&&<div className="error-banner"><strong>Request failed</strong><span>{error}</span><button onClick={()=>setError(null)}>×</button></div>}
      <LibraryPanel sourcePath={sourcePath} validFrom={validFrom} sources={sources} busy={busy} onSourcePath={setSourcePath} onValidFrom={setValidFrom} onImport={importSource}/>
      <section className="surface">
        {tab==="ask"&&<AskView question={question} result={result} busy={busy} workspaceReady={Boolean(workspace)} onQuestion={setQuestion} onAsk={ask} onOpenTrace={()=>setTab("trace")}/>}
        {tab==="trace"&&<TraceView result={result}/>}
        {tab==="graph"&&<GraphView graph={graph} onRefresh={refreshGraph} busy={busy}/>}
      </section>
    </div>
  </main>;
}
