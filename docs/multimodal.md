# Witness Multimodal Evidence

Phase 7 extends Witness evidence identity and retrieval to information that text flattening loses. The governing rule is unchanged: a visual answer must resolve to immutable source evidence with an exact locator.

## Phase 7 implementation order

1. visual evidence identity, page-region locators, content-addressed assets, and provider contracts;
2. PDF page/image/figure extraction adapters;
3. visual retrieval as an explicit route with Trace artifacts;
4. fusion with text candidates without losing modality/provenance;
5. visual citation rendering and page-region highlighting;
6. chart/table-aware evaluation fixtures and Lab coverage.

OCR or a vision model is deliberately not the foundation. Those are derived interpretation providers and may change without changing the identity of the source visual region.

## Visual evidence identity

A visual evidence object records:

- immutable source-version ID;
- visual modality: image, figure, chart, table, or generic page region;
- one-based source page;
- normalized top-left-origin bounding box;
- canonical locator such as `page:3#region:0.125000,0.250000,0.875000,0.750000`;
- SHA-256 of the exact visual payload;
- media type and optional pixel dimensions;
- optional source/derived label text.

The visual evidence ID is deterministic over source version, modality, locator, and asset hash. Display DPI and later OCR/model output therefore cannot silently change provenance.

## Content-addressed assets

Visual bytes are deduplicated by SHA-256. Multiple evidence regions may reference one asset without storing duplicate payloads. A visual evidence record is rejected if its source-version ID is not registered in Witness source metadata.

## Visual embeddings

`VisualEmbeddingProvider` defines a shared vector-space contract:

- `embed_images(...)`;
- `embed_texts(...)`;
- stable provider identity;
- fixed dimensions.

The deterministic hash provider exists only to test persistence, exact-vector search, ranking, and Trace plumbing offline. It is not presented as a semantic vision model. Production CLIP/SigLIP-style providers can implement the same interface later.

The initial `LocalVisualVectorIndex` uses exact cosine search, matching Witness's evidence-first policy of establishing measurable behavior before ANN optimization.


## PDF embedded-image extraction

The first concrete extractor uses pypdf's displayed image objects and the current content-stream transformation matrix. For a top-level image `Do` operation, Witness maps the image-space unit square through the six-value PDF CTM, clips it to the page crop box, converts PDF bottom-left coordinates to normalized top-left coordinates, and persists the resulting exact page region.

The adapter deliberately fails closed for cases it cannot yet locate reproducibly:

- visually rotated pages are skipped with a diagnostic;
- Form XObjects whose nested transform cannot yet be composed are not assigned guessed regions;
- broken/empty image payloads become warnings rather than evidence.

Pillow is a core Phase 7 dependency because pypdf requires it for image extraction. OCR is still not performed by this layer.


## Visual retrieval route

Visual retrieval is now an explicit transparent-router route. Queries containing visual terms such as `chart`, `figure`, `image`, `diagram`, or `table` request the route. If no visual index/provider is configured, Trace records the route as advisory rather than pretending it executed.

When configured, visual results are converted into the shared retrieval-candidate contract with:

- `evidence_kind = "visual"`;
- the immutable `visual_evidence_id`;
- the source-version ID;
- the exact page-region locator;
- the visual modality;
- a label suitable for deterministic baseline reranking/generation.

Visual candidates then participate in the same RRF and reranking stages as textual evidence. Fusion and reranking preserve the modality fields rather than flattening them away. ContextPack and validated citations also retain the visual evidence ID and modality.

Ask Trace includes a dedicated `retrieval.visual.completed` event with the visual provider identity and candidate list. This makes the route that caused a page region to reach the answer directly inspectable.


## Evidence viewer

Cited visual evidence can be opened directly from Ask or Trace. The desktop requests the immutable visual evidence record by ID and receives a bounded derived JPEG preview plus the original provenance metadata.

The viewer displays the extracted asset beside a normalized source-page map. The map is deliberately schematic rather than pretending to be a PDF renderer: its highlighted box is computed directly from the stored normalized region, while the extracted source asset is shown separately. The viewer also exposes the exact locator, source-version ID, original media type, and asset SHA-256.

Preview generation never changes visual evidence identity. It is a disposable presentation artifact derived from the content-addressed source asset.


## Semantic provider boundary

Witness deliberately separates visual evidence extraction from semantic visual retrieval.

PDF import always stores provenance-safe visual evidence when the visual store is available. A visual embedding provider is optional: without one, images remain inspectable/citable artifacts and the transparent router records visual requests as advisory rather than executing a meaningless similarity search.

The dependency-free `DeterministicHashVisualEmbeddingProvider` is a plumbing/test baseline only. It is not semantic and is not enabled by default in the desktop engine.

For real image-to-text retrieval, Witness includes an optional lazy `OpenClipVisualEmbeddingProvider`. Install the engine's `vision` extra and explicitly configure:

- `WITNESS_VISUAL_PROVIDER=openclip`;
- optional `WITNESS_OPENCLIP_MODEL`;
- optional `WITNESS_OPENCLIP_PRETRAINED`;
- optional `WITNESS_OPENCLIP_DEVICE`.

For deterministic plumbing experiments only, `WITNESS_VISUAL_PROVIDER=hash` remains available explicitly. Provider identity is persisted in routed Lab configuration snapshots. Provider selection is expected to move into the normal desktop provider configuration surface during Phase 8.
