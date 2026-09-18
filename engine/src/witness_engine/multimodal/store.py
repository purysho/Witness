"""SQLite persistence for content-addressed visual assets and evidence."""

from __future__ import annotations

from hashlib import sha256

from ..retrieval.index import LocalEvidenceIndex
from ..retrieval.temporal import LocalTemporalIndex
from .models import NormalizedRegion, VisualEvidence, VisualModality


class VisualEvidenceStore:
    def __init__(self, evidence_index: LocalEvidenceIndex) -> None:
        self.connection = evidence_index.connection
        # Visual evidence must resolve to the same immutable SourceVersion model
        # as text evidence. Initializing the temporal projection guarantees the
        # provenance table exists even before a visual record is registered.
        LocalTemporalIndex(evidence_index)
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS visual_assets (
                asset_sha256 TEXT PRIMARY KEY,
                media_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                payload BLOB NOT NULL
            );

            CREATE TABLE IF NOT EXISTS visual_evidence (
                visual_evidence_id TEXT PRIMARY KEY,
                source_version_id TEXT NOT NULL,
                modality TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                x0 REAL NOT NULL,
                y0 REAL NOT NULL,
                x1 REAL NOT NULL,
                y1 REAL NOT NULL,
                locator TEXT NOT NULL,
                asset_sha256 TEXT NOT NULL,
                media_type TEXT NOT NULL,
                width_px INTEGER,
                height_px INTEGER,
                label_text TEXT NOT NULL,
                FOREIGN KEY (asset_sha256)
                    REFERENCES visual_assets(asset_sha256)
            );

            CREATE INDEX IF NOT EXISTS idx_visual_evidence_source
                ON visual_evidence(source_version_id, page_number);
            CREATE INDEX IF NOT EXISTS idx_visual_evidence_asset
                ON visual_evidence(asset_sha256);
            """
        )

    def register(
        self,
        *,
        source_version_id: str,
        modality: VisualModality,
        page_number: int,
        region: NormalizedRegion,
        payload: bytes,
        media_type: str,
        width_px: int | None = None,
        height_px: int | None = None,
        label_text: str = "",
    ) -> VisualEvidence:
        if not payload:
            raise ValueError("visual evidence payload cannot be empty")

        source = self.connection.execute(
            """
            SELECT 1
            FROM source_version_metadata
            WHERE source_version_id = ?
            """,
            (source_version_id,),
        ).fetchone()
        if source is None:
            raise ValueError(
                "visual evidence must reference a registered source version"
            )

        digest = sha256(payload).hexdigest()
        existing_asset = self.connection.execute(
            """
            SELECT media_type
            FROM visual_assets
            WHERE asset_sha256 = ?
            """,
            (digest,),
        ).fetchone()
        if (
            existing_asset is not None
            and existing_asset["media_type"] != media_type
        ):
            raise ValueError(
                "content-identical visual asset was registered with a "
                "different media type"
            )

        evidence = VisualEvidence.create(
            source_version_id=source_version_id,
            modality=modality,
            page_number=page_number,
            region=region,
            asset_sha256=digest,
            media_type=media_type,
            width_px=width_px,
            height_px=height_px,
            label_text=label_text,
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO visual_assets (
                    asset_sha256, media_type, byte_size, payload
                ) VALUES (?, ?, ?, ?)
                """,
                (digest, media_type, len(payload), payload),
            )
            self.connection.execute(
                """
                INSERT OR IGNORE INTO visual_evidence (
                    visual_evidence_id, source_version_id, modality,
                    page_number, x0, y0, x1, y1, locator,
                    asset_sha256, media_type, width_px, height_px,
                    label_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.visual_evidence_id,
                    evidence.source_version_id,
                    evidence.modality.value,
                    evidence.page_number,
                    evidence.region.x0,
                    evidence.region.y0,
                    evidence.region.x1,
                    evidence.region.y1,
                    evidence.locator,
                    evidence.asset_sha256,
                    evidence.media_type,
                    evidence.width_px,
                    evidence.height_px,
                    evidence.label_text,
                ),
            )
        # The first registration of a visual identity is canonical. Returning
        # the persisted record avoids pretending later derived labels changed
        # immutable evidence.
        return self.load(evidence.visual_evidence_id)

    @staticmethod
    def _from_row(row) -> VisualEvidence:
        return VisualEvidence(
            visual_evidence_id=row["visual_evidence_id"],
            source_version_id=row["source_version_id"],
            modality=VisualModality(row["modality"]),
            page_number=int(row["page_number"]),
            region=NormalizedRegion(
                x0=float(row["x0"]),
                y0=float(row["y0"]),
                x1=float(row["x1"]),
                y1=float(row["y1"]),
            ),
            locator=row["locator"],
            asset_sha256=row["asset_sha256"],
            media_type=row["media_type"],
            width_px=row["width_px"],
            height_px=row["height_px"],
            label_text=row["label_text"],
        )

    def load(self, visual_evidence_id: str) -> VisualEvidence:
        row = self.connection.execute(
            """
            SELECT * FROM visual_evidence
            WHERE visual_evidence_id = ?
            """,
            (visual_evidence_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown visual evidence: {visual_evidence_id}")
        return self._from_row(row)

    def list(
        self,
        *,
        source_version_id: str | None = None,
        limit: int = 500,
    ) -> tuple[VisualEvidence, ...]:
        query = "SELECT * FROM visual_evidence"
        params: list[object] = []
        if source_version_id is not None:
            query += " WHERE source_version_id = ?"
            params.append(source_version_id)
        query += " ORDER BY source_version_id, page_number, locator LIMIT ?"
        params.append(max(1, min(limit, 5000)))
        rows = self.connection.execute(query, tuple(params)).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def asset_bytes(self, asset_sha256: str) -> bytes:
        row = self.connection.execute(
            "SELECT payload FROM visual_assets WHERE asset_sha256 = ?",
            (asset_sha256,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown visual asset: {asset_sha256}")
        return bytes(row["payload"])

    def asset_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM visual_assets"
            ).fetchone()[0]
        )

    def evidence_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM visual_evidence"
            ).fetchone()[0]
        )
