import type { AskResult } from "../../../../../contracts/generated/rpc";
import { StateBadge } from "../../components/StateBadge";

interface Props {
  question:string; result:AskResult|null; busy:boolean; workspaceReady:boolean;
  onQuestion:(value:string)=>void; onAsk:()=>void; onOpenTrace:()=>void;
  onOpenVisual:(visualEvidenceId:string)=>void;
}

export function AskView({question,result,busy,workspaceReady,onQuestion,onAsk,onOpenTrace,onOpenVisual}:Props) {
  return (
    <div className="view-grid ask-grid">
      <section className="panel ask-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">ASK</span><h2>Interrogate the evidence</h2></div>
          {result && <StateBadge state={result.answer.state}/>}
        </div>
        <textarea className="question-box" value={question} onChange={e=>onQuestion(e.target.value)}
          disabled={!workspaceReady}
          placeholder={workspaceReady
            ? "Ask a question that the indexed evidence can support…"
            : "Open a workspace before asking a question."} rows={4}/>
        <div className="ask-actions">
          <button className="primary" disabled={busy||!workspaceReady||!question.trim()} onClick={onAsk}>
            {busy ? "Running evidence pipeline…" : "Run Ask"}
          </button>
          {result && <button className="secondary" onClick={onOpenTrace}>Inspect trace</button>}
        </div>
        {result ? (
          <div className="answer-block">
            <div className="sufficiency-strip">
              <span>Coverage <strong>{Math.round(result.sufficiency.query_coverage*100)}%</strong></span>
              <span>Sources <strong>{result.sufficiency.independent_source_count}</strong></span>
              <span>Conflicts <strong>{result.sufficiency.unresolved_conflict_count}</strong></span>
            </div>
            {result.answer.sentences.map((sentence,index)=>(
              <p className="answer-sentence" key={`${index}-${sentence.text}`}>
                {sentence.text}
                {sentence.evidence_ids.map(id=>(
                  <button className="citation-chip" key={id} title={id}
                    onClick={()=>document.getElementById(`evidence-${id}`)?.scrollIntoView({behavior:"smooth",block:"center"})}>
                    {id.slice(0,7)}
                  </button>
                ))}
              </p>
            ))}
            <div className="reason-list">{result.sufficiency.reasons.map(reason=><span key={reason}>{reason}</span>)}</div>
          </div>
        ) : <div className="empty answer-empty">{workspaceReady
          ? "Answers appear here only after Witness has retrieved, reconciled, and checked the evidence."
          : "Open or create a workspace first. Then import evidence or try the local demo."}</div>}
      </section>
      <section className="panel evidence-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">EVIDENCE</span><h2>Selected context</h2></div>
          <span className="count">{result?.context.evidence.length ?? 0} items</span>
        </div>
        <div className="evidence-list">
          {result ? result.context.evidence.map(item=>(
            <article className="evidence-card" id={`evidence-${item.evidence_id}`} key={item.evidence_id}>
              <div className="evidence-topline">
                <span>#{item.rank}</span>
                <code>{item.evidence_id.slice(0,10)}</code>
              </div>
              <p>{item.text}</p>
              {item.evidence_kind === "visual" && item.visual_evidence_id && (
                <button
                  className="visual-open"
                  onClick={() => onOpenVisual(item.visual_evidence_id)}
                >
                  View {item.modality || "visual"} region
                </button>
              )}
              <footer>
                <span>{item.locator??"no locator"}</span>
                <span>{item.method}</span>
              </footer>
            </article>
          )) : <div className="empty">{workspaceReady
            ? "Run a question to inspect selected evidence."
            : "Selected evidence appears after a workspace is open and a question has run."}</div>}
        </div>
      </section>
    </div>
  );
}
