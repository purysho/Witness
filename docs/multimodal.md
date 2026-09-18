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
