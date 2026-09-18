import { useState } from "react";
import type { AskResult, TraceEvent } from "../../../../../contracts/generated/rpc";

function TraceRow({event}:{event:TraceEvent}) {
  const [open,setOpen]=useState(false);
  return (
    <article className="trace-row">
      <button className="trace-summary" onClick={()=>setOpen(v=>!v)}>
        <span className="trace-sequence">{String(event.sequence).padStart(2,"0")}</span>
        <strong>{event.stage}</strong>
        <span>{new Date(event.created_at).toLocaleTimeString()}</span>
        <span className="disclosure">{open?"−":"+"}</span>
      </button>
      {open && <pre>{JSON.stringify(event.payload,null,2)}</pre>}
    </article>
  );
}

export function TraceView({
  result,
  onOpenVisual,
}:{
  result:AskResult|null;
  onOpenVisual:(visualEvidenceId:string)=>void;
}) {
  if (!result) return (
    <section className="panel full-panel">
      <span className="eyebrow">TRACE</span><h2>No query run selected</h2>
      <div className="empty">Run Ask first. Trace shows structured route, retrieval, reconciliation, sufficiency, generation, and validation artifacts — never hidden chain-of-thought.</div>
    </section>
  );
  const routeTrace=result.retrieval.trace as {plan?:{routes?:Array<{route:string;requested:boolean;executable:boolean;reasons:string[]}>}};
  return (
    <div className="view-grid trace-grid">
      <section className="panel">
        <div className="panel-heading">
          <div><span className="eyebrow">TRACE</span><h2>Run {result.run_id.slice(0,12)}</h2></div>
          <span className="count">{result.trace.length} events</span>
        </div>
        <div className="route-grid">
          {routeTrace.plan?.routes?.map(route=>(
            <article className={`route-card ${route.requested?"route-active":""}`} key={route.route}>
              <strong>{route.route}</strong>
              <span>{route.requested&&route.executable?"executed":route.requested?"requested":"idle"}</span>
              <p>{route.reasons.join(" · ")}</p>
            </article>
          ))}
        </div>
        <div className="trace-list">{result.trace.map(event=><TraceRow event={event} key={event.sequence}/>)}</div>
      </section>
      <section className="panel audit-panel">
        <span className="eyebrow">AUDIT</span><h2>Evidence decision</h2>
        <dl className="audit-list">
          <div><dt>State</dt><dd>{result.sufficiency.state}</dd></div>
          <div><dt>Query coverage</dt><dd>{Math.round(result.sufficiency.query_coverage*100)}%</dd></div>
          <div><dt>Evidence</dt><dd>{result.sufficiency.evidence_count}</dd></div>
          <div><dt>Independent sources</dt><dd>{result.sufficiency.independent_source_count}</dd></div>
          <div><dt>Unresolved conflicts</dt><dd>{result.sufficiency.unresolved_conflict_count}</dd></div>
          <div><dt>Temporal satisfied</dt><dd>{result.sufficiency.temporal_requirement_satisfied?"yes":"no"}</dd></div>
        </dl>
        <h3>Citations</h3>
        <div className="citation-list">{result.answer.citations.map(c=>(
          <article key={c.evidence_id}>
            <code>{c.evidence_id.slice(0,12)}</code>
            <span>{c.locator??"no locator"}</span>
            <small>{c.source_version_id.slice(0,12)}</small>
            {c.evidence_kind === "visual" && c.visual_evidence_id && (
              <button
                className="visual-open"
                onClick={() => onOpenVisual(c.visual_evidence_id)}
              >
                Open {c.modality || "visual"}
              </button>
            )}
          </article>
        ))}</div>
      </section>
    </div>
  );
}
