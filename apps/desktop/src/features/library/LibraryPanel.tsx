import { useState } from "react";
import type {
  SourceVersionDetail,
  SourceVersionSummary,
} from "../../../../../contracts/generated/rpc";

type LifecycleAction = "archive" | "restore";

interface Props {
  sourcePath: string;
  validFrom: string;
  sources: SourceVersionSummary[];
  selectedSource: SourceVersionDetail | null;
  busy: boolean;
  workspaceReady: boolean;
  onSourcePath: (value: string) => void;
  onValidFrom: (value: string) => void;
  onBrowseSource: () => void;
  onImport: () => void;
  onInspectSource: (sourceVersionId: string) => Promise<void>;
  onArchiveSource: (sourceVersionId: string) => Promise<void>;
  onRestoreSource: (sourceVersionId: string) => Promise<void>;
  onClearSourceDetails: () => void;
}

function lifecycleLabel(source: SourceVersionSummary): string {
  if (source.archived) return "ARCHIVED";
  if (source.superseded_by_source_version_id) return "HISTORICAL";
  return "ACTIVE";
}

export function LibraryPanel({
  sourcePath,
  validFrom,
  sources,
  selectedSource,
  busy,
  workspaceReady,
  onSourcePath,
  onValidFrom,
  onBrowseSource,
  onImport,
  onInspectSource,
  onArchiveSource,
  onRestoreSource,
  onClearSourceDetails,
}: Props) {
  const [pendingLifecycle, setPendingLifecycle] = useState<{
    action: LifecycleAction;
    sourceVersionId: string;
    title: string;
  } | null>(null);

  const archivedCount = sources.filter((source) => source.archived).length;

  async function confirmLifecycle() {
    if (!pendingLifecycle) return;
    if (pendingLifecycle.action === "archive") {
      await onArchiveSource(pendingLifecycle.sourceVersionId);
    } else {
      await onRestoreSource(pendingLifecycle.sourceVersionId);
    }
    setPendingLifecycle(null);
  }

  return (
    <section className="panel library-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">LIBRARY</span>
          <h2>Evidence sources</h2>
        </div>
        <span className="count">
          {sources.length} versions · {archivedCount} archived
        </span>
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
              <article
                className={
                  "source-row " +
                  (selectedSource?.source_version_id === source.source_version_id
                    ? "source-row-selected"
                    : "")
                }
                key={source.source_version_id}
              >
                <div className="source-row-main">
                  <div className="source-title-line">
                    <strong>{source.title}</strong>
                    <span
                      className={
                        "lifecycle-badge lifecycle-" +
                        lifecycleLabel(source).toLowerCase()
                      }
                    >
                      {lifecycleLabel(source)}
                    </span>
                  </div>
                  <span>{source.media_type}</span>
                </div>
                <div className="source-meta">
                  <code>{source.source_version_id.slice(0, 12)}</code>
                  <span>{source.valid_from}</span>
                </div>
                <button
                  className="secondary source-detail-button"
                  disabled={busy}
                  onClick={() => void onInspectSource(source.source_version_id)}
                >
                  Details
                </button>
              </article>
            ))
          )}
        </div>
      )}

      {selectedSource && (
        <section className="source-detail-panel">
          <div className="source-detail-heading">
            <div>
              <span className="eyebrow">SOURCE VERSION</span>
              <h3>{selectedSource.title}</h3>
            </div>
            <button className="secondary" onClick={onClearSourceDetails}>
              Close
            </button>
          </div>

          <dl className="source-detail-grid">
            <div>
              <dt>Lifecycle</dt>
              <dd>{lifecycleLabel(selectedSource)}</dd>
            </div>
            <div>
              <dt>Chunks</dt>
              <dd>{selectedSource.chunk_count}</dd>
            </div>
            <div>
              <dt>Valid from</dt>
              <dd>{selectedSource.valid_from}</dd>
            </div>
            <div>
              <dt>Valid to</dt>
              <dd>{selectedSource.valid_to ?? "open"}</dd>
            </div>
            <div className="source-detail-wide">
              <dt>Source path</dt>
              <dd>{selectedSource.source_path}</dd>
            </div>
            <div className="source-detail-wide">
              <dt>Version ID</dt>
              <dd><code>{selectedSource.source_version_id}</code></dd>
            </div>
          </dl>

          <div className="version-chain">
            <div className="version-chain-heading">
              <span>VERSION CHAIN</span>
              <small>{selectedSource.version_chain.length} immutable versions</small>
            </div>
            {selectedSource.version_chain.map((version) => (
              <article
                className={
                  "version-chain-row " +
                  (version.source_version_id === selectedSource.source_version_id
                    ? "version-chain-current"
                    : "")
                }
                key={version.source_version_id}
              >
                <span className="version-chain-state">
                  {version.archived
                    ? "ARCHIVED"
                    : version.superseded_by_source_version_id
                      ? "HISTORICAL"
                      : "ACTIVE"}
                </span>
                <code>{version.source_version_id.slice(0, 12)}</code>
                <span>{version.valid_from}</span>
              </article>
            ))}
          </div>

          <div className="source-lifecycle-actions">
            <div>
              <strong>Non-destructive lifecycle</strong>
              <small>
                Archive keeps canonical evidence, citations, and prior Trace
                history. It only changes eligibility for new ordinary retrieval.
              </small>
            </div>
            <button
              className={selectedSource.archived ? "primary" : "secondary danger-action"}
              disabled={busy}
              onClick={() =>
                setPendingLifecycle({
                  action: selectedSource.archived ? "restore" : "archive",
                  sourceVersionId: selectedSource.source_version_id,
                  title: selectedSource.title,
                })
              }
            >
              {selectedSource.archived ? "Restore version" : "Archive version"}
            </button>
          </div>

          {pendingLifecycle &&
            pendingLifecycle.sourceVersionId === selectedSource.source_version_id && (
              <div className="lifecycle-confirm">
                <div>
                  <strong>
                    {pendingLifecycle.action === "archive"
                      ? "Archive this source version?"
                      : "Restore this source version?"}
                  </strong>
                  <span>
                    {pendingLifecycle.action === "archive"
                      ? "Evidence and old citations remain intact. Archived versions are excluded from normal retrieval; if this is the current version, Witness will not silently fall back to an older superseded version."
                      : "The version will become eligible again according to its immutable version chain and normal current-version rules."}
                  </span>
                </div>
                <div className="lifecycle-confirm-actions">
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => setPendingLifecycle(null)}
                  >
                    Cancel
                  </button>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => void confirmLifecycle()}
                  >
                    Confirm {pendingLifecycle.action}
                  </button>
                </div>
              </div>
            )}
        </section>
      )}
    </section>
  );
}
