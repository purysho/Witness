import type { SourceVersionSummary } from "../../../../../contracts/generated/rpc";

interface Props {
  sourcePath: string;
  validFrom: string;
  sources: SourceVersionSummary[];
  busy: boolean;
  workspaceReady: boolean;
  onSourcePath: (value: string) => void;
  onValidFrom: (value: string) => void;
  onBrowseSource: () => void;
  onImport: () => void;
}

export function LibraryPanel({
  sourcePath,
  validFrom,
  sources,
  busy,
  workspaceReady,
  onSourcePath,
  onValidFrom,
  onBrowseSource,
  onImport,
}: Props) {
  return (
    <section className="panel library-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">LIBRARY</span>
          <h2>Evidence sources</h2>
        </div>
        <span className="count">{sources.length} versions</span>
      </div>

      <div className="import-row">
        <div className="field grow">
          <span>Local file</span>
          <div className="path-picker">
            <input
              value={sourcePath}
              onChange={(event) => onSourcePath(event.target.value)}
              placeholder="Choose a local evidence file"
              disabled={!workspaceReady}
            />
            <button
              className="secondary"
              disabled={busy || !workspaceReady}
              onClick={onBrowseSource}
            >
              Browse
            </button>
          </div>
        </div>

        <label className="field date-field">
          <span>Valid from · optional</span>
          <input
            value={validFrom}
            onChange={(event) => onValidFrom(event.target.value)}
            placeholder="2026-01-01T00:00:00+00:00"
            disabled={!workspaceReady}
          />
        </label>

        <button
          className="primary"
          disabled={busy || !workspaceReady || !sourcePath.trim()}
          onClick={onImport}
        >
          Index source
        </button>
      </div>

      {!workspaceReady ? (
        <div className="empty library-locked">
          Open a workspace before adding evidence. Witness keeps every imported
          source version, index, run, and evaluation inside that local workspace.
        </div>
      ) : (
        <div className="source-list">
          {sources.length === 0 ? (
            <div className="empty">
              No evidence has been indexed in this workspace yet. Choose a local
              file to build the first evidence source.
            </div>
          ) : (
            sources.map((source) => (
              <article className="source-row" key={source.source_version_id}>
                <div>
                  <strong>{source.title}</strong>
                  <span>{source.media_type}</span>
                </div>
                <div className="source-meta">
                  <code>{source.source_version_id.slice(0, 12)}</code>
                  <span>{source.valid_from}</span>
                </div>
              </article>
            ))
          )}
        </div>
      )}
    </section>
  );
}
