"""
IncidentIQ - Vector Store
Manages incident embeddings for semantic retrieval using ChromaDB (local)
or Pinecone (production). Supports 1,200+ historical incident embeddings.
"""
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from backend.bedrock.client import bedrock_client
from backend.config import config

logger = logging.getLogger(__name__)


@dataclass
class IncidentRecord:
    incident_id: str
    title: str
    description: str
    root_cause: str
    mitigation: str
    severity: str
    service: str
    resolution_time_minutes: int
    tags: list[str]
    timestamp: str
    embedding: Optional[list[float]] = None


@dataclass
class RetrievalResult:
    incident: IncidentRecord
    similarity_score: float
    rank: int


class VectorStore:
    """
    Manages the incident knowledge base with semantic search.
    Supports ChromaDB for local/dev and Pinecone for production.
    """

    def __init__(self):
        self.provider = config.vector_db.provider
        self.collection_name = config.vector_db.collection_name
        self._collection = None
        self._pinecone_index = None

    def _get_chroma_collection(self):
        """Lazy-initialize ChromaDB collection."""
        if self._collection is None:
            try:
                import chromadb
                client = chromadb.PersistentClient(path=config.vector_db.chroma_path)
                self._collection = client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("ChromaDB collection '%s' ready.", self.collection_name)
            except ImportError:
                raise RuntimeError(
                    "chromadb not installed. Run: pip install chromadb"
                )
        return self._collection

    def _get_pinecone_index(self):
        """Lazy-initialize Pinecone index."""
        if self._pinecone_index is None:
            try:
                from pinecone import Pinecone
                pc = Pinecone(api_key=config.vector_db.pinecone_api_key)
                self._pinecone_index = pc.Index(config.vector_db.pinecone_index)
                logger.info("Pinecone index '%s' ready.", config.vector_db.pinecone_index)
            except ImportError:
                raise RuntimeError(
                    "pinecone-client not installed. Run: pip install pinecone-client"
                )
        return self._pinecone_index

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding using Amazon Titan Embeddings V2."""
        return bedrock_client.embed(text)

    def upsert_incident(self, incident: IncidentRecord) -> str:
        """
        Embed and store an incident record.
        Returns the stored document ID.
        """
        # Build rich text for embedding
        embed_text = (
            f"Title: {incident.title}\n"
            f"Description: {incident.description}\n"
            f"Root Cause: {incident.root_cause}\n"
            f"Service: {incident.service}\n"
            f"Severity: {incident.severity}\n"
            f"Tags: {', '.join(incident.tags)}"
        )
        embedding = self.embed_text(embed_text)
        doc_id = incident.incident_id or str(uuid.uuid4())

        metadata = {
            "incident_id": incident.incident_id,
            "title": incident.title,
            "root_cause": incident.root_cause,
            "mitigation": incident.mitigation,
            "severity": incident.severity,
            "service": incident.service,
            "resolution_time_minutes": incident.resolution_time_minutes,
            "tags": ",".join(incident.tags),
            "timestamp": incident.timestamp,
        }

        if self.provider == "chroma":
            collection = self._get_chroma_collection()
            collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[embed_text],
                metadatas=[metadata],
            )
        elif self.provider == "pinecone":
            index = self._get_pinecone_index()
            index.upsert(vectors=[(doc_id, embedding, metadata)])

        logger.info("Upserted incident %s to vector store.", doc_id)
        return doc_id

    def search_similar_incidents(
        self,
        query: str,
        top_k: int = 5,
        service_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
    ) -> list[RetrievalResult]:
        """
        Semantic search for similar historical incidents.
        Returns ranked results with similarity scores.
        """
        query_embedding = self.embed_text(query)
        results = []

        if self.provider == "chroma":
            collection = self._get_chroma_collection()
            where_filter = {}
            if service_filter:
                where_filter["service"] = service_filter
            if severity_filter:
                where_filter["severity"] = severity_filter

            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": top_k,
                "include": ["metadatas", "distances", "documents"],
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            chroma_results = collection.query(**query_kwargs)

            for i, (metadata, distance) in enumerate(
                zip(chroma_results["metadatas"][0], chroma_results["distances"][0])
            ):
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                similarity = 1 - (distance / 2)
                incident = IncidentRecord(
                    incident_id=metadata.get("incident_id", ""),
                    title=metadata.get("title", ""),
                    description=chroma_results["documents"][0][i],
                    root_cause=metadata.get("root_cause", ""),
                    mitigation=metadata.get("mitigation", ""),
                    severity=metadata.get("severity", ""),
                    service=metadata.get("service", ""),
                    resolution_time_minutes=int(
                        metadata.get("resolution_time_minutes", 0)
                    ),
                    tags=metadata.get("tags", "").split(","),
                    timestamp=metadata.get("timestamp", ""),
                )
                results.append(
                    RetrievalResult(
                        incident=incident,
                        similarity_score=round(similarity, 4),
                        rank=i + 1,
                    )
                )

        elif self.provider == "pinecone":
            index = self._get_pinecone_index()
            filter_dict = {}
            if service_filter:
                filter_dict["service"] = {"$eq": service_filter}
            if severity_filter:
                filter_dict["severity"] = {"$eq": severity_filter}

            pinecone_results = index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=filter_dict if filter_dict else None,
            )
            for i, match in enumerate(pinecone_results["matches"]):
                meta = match["metadata"]
                incident = IncidentRecord(
                    incident_id=meta.get("incident_id", ""),
                    title=meta.get("title", ""),
                    description=meta.get("description", ""),
                    root_cause=meta.get("root_cause", ""),
                    mitigation=meta.get("mitigation", ""),
                    severity=meta.get("severity", ""),
                    service=meta.get("service", ""),
                    resolution_time_minutes=int(meta.get("resolution_time_minutes", 0)),
                    tags=meta.get("tags", "").split(","),
                    timestamp=meta.get("timestamp", ""),
                )
                results.append(
                    RetrievalResult(
                        incident=incident,
                        similarity_score=round(match["score"], 4),
                        rank=i + 1,
                    )
                )

        logger.info(
            "Found %d similar incidents for query (top similarity: %.2f)",
            len(results),
            results[0].similarity_score if results else 0,
        )
        return results

    def format_retrieval_context(self, results: list[RetrievalResult]) -> str:
        """Format retrieval results as context for LLM prompts."""
        if not results:
            return "No similar historical incidents found."

        lines = ["## Similar Historical Incidents\n"]
        for r in results:
            lines.append(
                f"### [{r.rank}] {r.incident.title} (Similarity: {r.similarity_score:.0%})\n"
                f"- **Incident ID**: {r.incident.incident_id}\n"
                f"- **Service**: {r.incident.service} | **Severity**: {r.incident.severity}\n"
                f"- **Root Cause**: {r.incident.root_cause}\n"
                f"- **Mitigation**: {r.incident.mitigation}\n"
                f"- **Resolution Time**: {r.incident.resolution_time_minutes} min\n"
                f"- **Timestamp**: {r.incident.timestamp}\n"
            )
        return "\n".join(lines)


# Singleton
vector_store = VectorStore()
