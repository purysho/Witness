import { useEffect, useState } from "react";
import type { ProviderSnapshot } from "../../../../../contracts/generated/rpc";

interface Props {
  snapshot: ProviderSnapshot;
  busy: boolean;
  onApply: (
    embeddingDimensions: number,
    visualMode: "off" | "hash",
    visualDimensions: number,
  ) => void;
}

const DIMENSIONS = [32, 64, 128, 256] as const;

export function ProviderPanel({
  snapshot,
  busy,
  onApply,
}: Props) {
  const [embeddingDimensions, setEmbeddingDimensions] = useState(
    snapshot.settings.embedding_dimensions,
  );
  const [visualMode, setVisualMode] = useState<"off" | "hash">(
    snapshot.settings.visual_mode,
  );
  const [visualDimensions, setVisualDimensions] = useState(
    snapshot.settings.visual_dimensions,
  );

  useEffect(() => {
    setEmbeddingDimensions(snapshot.settings.embedding_dimensions);
    setVisualMode(snapshot.settings.visual_mode);
    setVisualDimensions(snapshot.settings.visual_dimensions);
  }, [snapshot]);

  const visualLocked = snapshot.visual.config_source === "environment";
  const reindexRequired =
    snapshot.embedding.reindex_required ||
    snapshot.visual.reindex_required;

  return (
    <section className="provider-panel">
      <div className="provider-heading">
        <div>
          <span className="eyebrow">PROVIDERS</span>
          <strong>Local provider configuration</strong>
        </div>
        <span className={reindexRequired ? "provider-dirty" : "provider-clean"}>
          {reindexRequired ? "REINDEX REQUIRED" : "INDEXES CURRENT"}
        </span>
      </div>

      <div className="provider-grid">
        <label className="field">
          <span>Text embedding</span>
          <select
            value={embeddingDimensions}
            disabled={busy}
            onChange={(event) =>
              setEmbeddingDimensions(Number(event.target.value))
            }
          >
            {DIMENSIONS.map((value) => (
              <option key={value} value={value}>
                Deterministic hash · {value}d
              </option>
            ))}
          </select>
          <small>{snapshot.embedding.provider_id}</small>
        </label>

        <label className="field">
          <span>Visual retrieval</span>
          <select
            value={visualMode}
            disabled={busy || visualLocked}
            onChange={(event) =>
              setVisualMode(event.target.value as "off" | "hash")
            }
          >
            <option value="off">Off</option>
            <option value="hash">Deterministic visual hash</option>
          </select>
          <small>
            {visualLocked
              ? "Environment override · " + (snapshot.visual.provider_id ?? "off")
              : snapshot.visual.provider_id ?? "No active visual provider"}
          </small>
        </label>

        <label className="field">
          <span>Visual dimensions</span>
          <select
            value={visualDimensions}
            disabled={busy || visualLocked || visualMode === "off"}
            onChange={(event) =>
              setVisualDimensions(Number(event.target.value))
            }
          >
            {DIMENSIONS.map((value) => (
              <option key={value} value={value}>
                {value}d
              </option>
            ))}
          </select>
          <small>
            Workspace setting; environment overrides remain authoritative.
          </small>
        </label>

        <div className="provider-fixed">
          <span>Fixed V1 baselines</span>
          <small>Reranker · {snapshot.reranker.provider_id}</small>
          <small>Generator · {snapshot.generator.provider_id}</small>
        </div>

        <div className="provider-secret-note">
          <strong>NO SECRETS STORED</strong>
          <span>{snapshot.secret_policy}</span>
        </div>

        <button
          className="secondary provider-apply"
          disabled={busy}
          onClick={() =>
            onApply(
              embeddingDimensions,
              visualMode,
              visualDimensions,
            )
          }
        >
          Apply provider settings
        </button>
      </div>
    </section>
  );
}
