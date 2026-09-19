import { useEffect, useState } from "react";
import type { ProviderSnapshot } from "../../../../../contracts/generated/rpc";

interface Props {
  snapshot: ProviderSnapshot;
  busy: boolean;
  onApply: (
    embeddingMode: "hash" | "sentence-transformers",
    embeddingModel: string,
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
  const [embeddingMode, setEmbeddingMode] = useState<
    "hash" | "sentence-transformers"
  >(snapshot.settings.embedding_mode);
  const [embeddingModel, setEmbeddingModel] = useState(
    snapshot.settings.embedding_model,
  );
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
    setEmbeddingMode(snapshot.settings.embedding_mode);
    setEmbeddingModel(snapshot.settings.embedding_model);
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
            value={embeddingMode}
            disabled={busy}
            onChange={(event) =>
              setEmbeddingMode(
                event.target.value as "hash" | "sentence-transformers",
              )
            }
          >
            <option value="hash">Deterministic hash</option>
            <option
              value="sentence-transformers"
              disabled={!snapshot.semantic.dependency_available}
            >
              Semantic MiniLM · local only
            </option>
          </select>
          <small>
            {embeddingMode === "sentence-transformers"
              ? snapshot.semantic.dependency_available
                ? "Optional semantic provider · local cached model only"
                : "Optional dependency unavailable in this installation"
              : "Guaranteed offline deterministic baseline"}
          </small>
        </label>

        {embeddingMode === "hash" ? (
          <label className="field">
            <span>Hash dimensions</span>
            <select
              value={embeddingDimensions}
              disabled={busy}
              onChange={(event) =>
                setEmbeddingDimensions(Number(event.target.value))
              }
            >
              {DIMENSIONS.map((value) => (
                <option key={value} value={value}>
                  {value}d
                </option>
              ))}
            </select>
            <small>{snapshot.embedding.provider_id}</small>
          </label>
        ) : (
          <label className="field">
            <span>Semantic model</span>
            <select
              value={embeddingModel}
              disabled={busy || !snapshot.semantic.dependency_available}
              onChange={(event) => setEmbeddingModel(event.target.value)}
            >
              <option value={snapshot.semantic.model}>
                {snapshot.semantic.model}
              </option>
            </select>
            <small>
              {snapshot.embedding.available
                ? snapshot.embedding.provider_id
                : snapshot.embedding.availability_error ??
                  "Model must already exist in the local cache."}
            </small>
          </label>
        )}

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
              embeddingMode,
              embeddingModel,
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
