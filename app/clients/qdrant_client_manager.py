

import asyncio
from http import client
from typing import  Optional


from qdrant_client import  AsyncQdrantClient
from qdrant_client.conversions.common_types import UpdateResult
from qdrant_client.http.models import VectorParams, Distance, PointStruct, QueryResponse, Filter, FieldCondition, \
    MatchValue

from app.clients.embedding_client_manager import EmbeddingClientManager
from app.conf.app_config import QdrantConfig, app_config



class QdrantClientManager:


    #automatically run when new a instance of QdrantConfig
    def __init__(self, qdrant_config: QdrantConfig):
        self.qdrant_config = qdrant_config

        self.client: Optional[AsyncQdrantClient] = None

    def _get_url(self)->str:
        return f"http://{self.qdrant_config.host}:{self.qdrant_config.port}"

    def init(self):
        if self.client is None:

            self.client = AsyncQdrantClient(url = self._get_url())

    async def close(self):
        await self.client.close()




# 创建一个全局的管理器对象
# 后续项目中的其他模块都通过它来获取同一套 Qdrant 客户端
qdrant_client_manager = QdrantClientManager(app_config.qdrant)
embedding_client = EmbeddingClientManager(app_config.embedding)

if __name__ == '__main__':

    qdrant_client_manager.init()
    embedding_client.init()

    embedding_client = embedding_client.client
    # async def main():
    #     qdrant.init()
    #
    #     try:
    #         collections = await qdrant.client.get_collections()
    #         print(collections)
    #     finally:
    #         await qdrant.close()
    coll_name = "test"

    client = qdrant_client_manager.client
    async def test_collections():

        flag = await client.collection_exists(collection_name=coll_name)

        if not flag:
            flag = await client.create_collection(
                collection_name=coll_name,
                vectors_config=VectorParams(
                    size=app_config.qdrant.embedding_size,
                    distance=Distance.COSINE
                )
            )

            print("创建集合结果", flag)

    async def test_add_ponits():

        keywords = [
            "人工智能",
            "机器学习",
            "深度学习",
            "数据分析",
            "数据可视化",
            "云计算",
            "大数据",
            "自动化",
            "数字化转型",
            "用户体验",
            "用户增长",
            "内容营销",
            "品牌建设",
            "社交媒体",
            "搜索引擎优化",
            "关键词研究",
            "转化率",
            "私域流量",
            "客户关系管理",
            "项目管理",
            "敏捷开发",
            "产品设计",
            "商业模式",
            "市场调研",
            "竞争分析",
            "创业",
            "融资",
            "投资",
            "财务规划",
            "风险管理",
            "供应链",
            "电子商务",
            "跨境电商",
            "直播带货",
            "短视频",
            "内容创作",
            "文案写作",
            "平面设计",
            "视频剪辑",
            "摄影",
            "职场技能",
            "时间管理",
            "沟通技巧",
            "领导力",
            "团队协作",
            "职业发展",
            "简历优化",
            "面试技巧",
            "学习方法",
            "效率工具",
        ]

        points = [PointStruct(id=i,
                     vector=await embedding_client.aembed_query(keyword),

                     payload={"keyword":keyword}

                     ) for i, keyword in enumerate(keywords)]


        result:UpdateResult = await client.upsert(
            collection_name=coll_name,
            points= points
        )
        print(result)

    async def test_search():

        embedded_query = await embedding_client.aembed_query("项目")

        result: QueryResponse = await client.query_points(
            collection_name=coll_name,
            query= embedded_query,
            limit=10,
            score_threshold=0.6,
            query_filter=Filter(
                must=[FieldCondition(key="keyword", match=MatchValue(value="项目管理"))]
            ),
        )

        payload_list = [point.payload for point in result.points]
        print(payload_list)
    asyncio.run(test_search())

