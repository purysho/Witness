import type { SourceVersionSummary } from "../../../../../contracts/generated/rpc";

interface Props {
  sourcePath:string; validFrom:string; sources:SourceVersionSummary[]; busy:boolean;
  onSourcePath:(value:string)=>void; onValidFrom:(value:string)=>void; onImport:()=>void;
}

export function LibraryPanel({sourcePath,validFrom,sources,busy,onSourcePath,onValidFrom,onImport}:Props) {
  return (
    <section className="panel library-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">LIBRARY</span><h2>Evidence sources</h2></div>
        <span className="count">{sources.length} versions</span>
      </div>
      <div className="import-row">
        <label className="field grow">
          <span>Local file path</span>
          <input value={sourcePath} onChange={e=>onSourcePath(e.target.value)} placeholder="C:\research\architecture.md" />
        </label>
        <label className="field date-field">
          <span>Valid from · optional</span>
          <input value={validFrom} onChange={e=>onValidFrom(e.target.value)} placeholder="2026-01-01T00:00:00+00:00" />
        </label>
        <button className="primary" disabled={busy||!sourcePath.trim()} onClick={onImport}>Index source</button>
      </div>
      <div className="source-list">
        {sources.length===0 ? <div className="empty">No evidence has been indexed in this workspace yet.</div> :
          sources.map(source=>(
            <article className="source-row" key={source.source_version_id}>
              <div><strong>{source.title}</strong><span>{source.media_type}</span></div>
              <div className="source-meta"><code>{source.source_version_id.slice(0,12)}</code><span>{source.valid_from}</span></div>
            </article>
          ))
        }
      </div>
    </section>
  );
}
