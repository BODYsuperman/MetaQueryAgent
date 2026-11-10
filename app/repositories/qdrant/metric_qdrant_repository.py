from qdrant_client import AsyncQdrantClient
from qdrant_client.conversions.common_types import VectorParams
from qdrant_client.http.models import Distance, PointStruct

from app.conf.app_config import app_config
from app.entities.metric_info import MetricInfo


class MetricQdrantRepository:
    collection_name = "metric_info_collection"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async  def ensure_collection(self):
        if not await self.client.collection_exists(self.collection_name):
            await self.client.create_collection(

                collection_name= self.collection_name,
                vectors_config= VectorParams(
                    size= app_config.qdrant.embedding_size,
                    distance= Distance.COSINE
                )
            )

    async def upsert(self,
                     ids:list[str],
                     embeddings:list[list[float]],
                     payloads:list[dict],
                     batch_size: int = 5
                     ):

        zipped = list(zip(ids, embeddings, payloads))

        for i in range(0, len(zipped), batch_size):
            batch = zipped[i: i+ batch_size]
            batch_points = [
                PointStruct(id = id, vector=embedding, payload=payload)
                for id, embedding, payload in batch
            ]
            await self.client.upsert(
                collection_name=self.collection_name, points=batch_points
            )
    async def search(
        self,
        embedding: list[float],
        score_threshold: float = 0.6,
        limit: int = 20,
    ) -> list[MetricInfo]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [MetricInfo(**point.payload) for point in result.points]