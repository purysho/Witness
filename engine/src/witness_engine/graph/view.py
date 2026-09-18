"""Read-only graph projection used by the Graph desktop surface."""

from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any

from ..evidence.reconcile import EvidenceReconciler
from ..retrieval.graph import LocalEvidenceGraph
from ..retrieval.index import LocalEvidenceIndex
from ..retrieval.temporal import LocalTemporalIndex

@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    label: str
    metadata: dict[str, Any]

@dataclass(frozen=True)
class GraphEdge:
    id: str
    source: str
    target: str
    relation: str
    metadata: dict[str, Any]

@dataclass(frozen=True)
class GraphSnapshot:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    def to_dict(self) -> dict:
        return asdict(self)

def _short(text: str, limit: int = 92) -> str:
    value = " ".join(text.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"

def build_graph_snapshot(index: LocalEvidenceIndex, *, limit: int = 160) -> GraphSnapshot:
    """Return a bounded graph whose evidence nodes resolve to source locators."""
    if limit <= 0:
        return GraphSnapshot((), ())

    LocalEvidenceGraph(index)
    LocalTemporalIndex(index)
    EvidenceReconciler(index)

    connection = index.connection
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}

    for row in connection.execute(
        """SELECT source_version_id, title, source_path, valid_from, valid_to
           FROM source_version_metadata
           ORDER BY valid_from DESC, source_version_id LIMIT ?""",
        (limit,),
    ).fetchall():
        node_id = f"source:{row['source_version_id']}"
        nodes[node_id] = GraphNode(node_id, "source", str(row["title"]), {
            "source_version_id": row["source_version_id"],
            "path": row["source_path"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
        })

    for row in connection.execute(
        "SELECT claim_id, text FROM graph_claims ORDER BY claim_id LIMIT ?",
        (limit,),
    ).fetchall():
        node_id = f"claim:{row['claim_id']}"
        nodes[node_id] = GraphNode(node_id, "claim", _short(str(row["text"])), {
            "claim_id": row["claim_id"], "text": row["text"]
        })

    for row in connection.execute(
        "SELECT entity_id, canonical_name FROM graph_entities ORDER BY canonical_name, entity_id LIMIT ?",
        (limit,),
    ).fetchall():
        node_id = f"entity:{row['entity_id']}"
        nodes[node_id] = GraphNode(node_id, "entity", str(row["canonical_name"]), {
            "entity_id": row["entity_id"]
        })

    evidence_rows = connection.execute(
        """SELECT DISTINCT c.chunk_id, c.text, c.source_version_id, c.locator
           FROM indexed_chunks AS c
           LEFT JOIN graph_claim_evidence AS ge ON ge.chunk_id = c.chunk_id
           LEFT JOIN evidence_relations AS er
             ON er.left_chunk_id = c.chunk_id OR er.right_chunk_id = c.chunk_id
           WHERE ge.chunk_id IS NOT NULL OR er.relation_id IS NOT NULL
           ORDER BY c.chunk_id LIMIT ?""",
        (limit,),
    ).fetchall()
    for row in evidence_rows:
        node_id = f"evidence:{row['chunk_id']}"
        nodes[node_id] = GraphNode(node_id, "evidence", _short(str(row["text"])), {
            "chunk_id": row["chunk_id"], "text": row["text"],
            "source_version_id": row["source_version_id"], "locator": row["locator"],
        })
        source_id = f"source:{row['source_version_id']}"
        if source_id in nodes:
            edge_id = f"contains:{row['source_version_id']}:{row['chunk_id']}"
            edges[edge_id] = GraphEdge(edge_id, source_id, node_id, "CONTAINS", {"locator": row["locator"]})

    for row in connection.execute(
        "SELECT entity_id, claim_id FROM graph_claim_entities ORDER BY entity_id, claim_id LIMIT ?",
        (limit * 2,),
    ).fetchall():
        source, target = f"entity:{row['entity_id']}", f"claim:{row['claim_id']}"
        if source in nodes and target in nodes:
            edge_id = f"mentions:{row['entity_id']}:{row['claim_id']}"
            edges[edge_id] = GraphEdge(edge_id, source, target, "MENTIONS", {})

    for row in connection.execute(
        "SELECT claim_id, chunk_id, relation FROM graph_claim_evidence ORDER BY claim_id, chunk_id LIMIT ?",
        (limit * 2,),
    ).fetchall():
        source, target = f"claim:{row['claim_id']}", f"evidence:{row['chunk_id']}"
        if source in nodes and target in nodes:
            edge_id = f"{row['relation']}:{row['claim_id']}:{row['chunk_id']}"
            edges[edge_id] = GraphEdge(edge_id, source, target, str(row["relation"]).upper(), {})

    for row in connection.execute(
        """SELECT relation_id, relation, left_chunk_id, right_chunk_id, reason
           FROM evidence_relations ORDER BY relation_id LIMIT ?""",
        (limit * 2,),
    ).fetchall():
        source, target = f"evidence:{row['left_chunk_id']}", f"evidence:{row['right_chunk_id']}"
        if source in nodes and target in nodes:
            edge_id = str(row["relation_id"])
            edges[edge_id] = GraphEdge(edge_id, source, target, str(row["relation"]), {"reason": row["reason"]})

    referenced = {value for edge in edges.values() for value in (edge.source, edge.target)}
    filtered = tuple(node for node in nodes.values() if node.kind == "source" or node.id in referenced)
    return GraphSnapshot(filtered[:limit], tuple(edges.values())[: limit * 2])
