import type { VisualEvidencePreview } from "../../../../../contracts/generated/rpc";

interface Props {
  preview: VisualEvidencePreview;
  onClose: () => void;
}

export function VisualEvidenceViewer({ preview, onClose }: Props) {
  const item = preview.evidence;
  const regionStyle = {
    left: (item.region.x0 * 100) + "%",
    top: (item.region.y0 * 100) + "%",
    width: ((item.region.x1 - item.region.x0) * 100) + "%",
    height: ((item.region.y1 - item.region.y0) * 100) + "%",
  };

  return (
    <div className="visual-viewer-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="visual-viewer panel"
        role="dialog"
        aria-modal="true"
        aria-label="Visual evidence"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="panel-heading">
          <div>
            <span className="eyebrow">VISUAL EVIDENCE</span>
            <h2>{item.label_text || item.modality}</h2>
          </div>
          <button className="secondary" onClick={onClose}>Close</button>
        </div>

        <div className="visual-viewer-grid">
          <div>
            <span className="viewer-label">Extracted asset</span>
            <div className="visual-asset-frame">
              {preview.preview_data_url ? (
                <img src={preview.preview_data_url} alt={item.label_text || item.modality} />
              ) : (
                <div className="empty">{preview.preview_warning || "Preview unavailable."}</div>
              )}
            </div>
          </div>

          <div>
            <span className="viewer-label">Normalized page map · page {item.page_number}</span>
            <div className="visual-page-map" aria-label="Normalized source-page region map">
              <div className="visual-region-box" style={regionStyle} />
            </div>
            <small className="visual-map-note">
              Schematic page geometry. The highlighted box is the exact normalized locator; the extracted source asset is shown separately.
            </small>
          </div>
        </div>

        <dl className="visual-metadata">
          <div><dt>Modality</dt><dd>{item.modality}</dd></div>
          <div><dt>Locator</dt><dd><code>{item.locator}</code></dd></div>
          <div><dt>Source version</dt><dd><code>{item.source_version_id}</code></dd></div>
          <div><dt>Asset SHA-256</dt><dd><code>{item.asset_sha256}</code></dd></div>
          <div><dt>Original media</dt><dd>{item.media_type}</dd></div>
        </dl>
      </section>
    </div>
  );
}
