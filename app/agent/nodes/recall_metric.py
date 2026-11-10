from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime
from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.entities.metric_info import MetricInfo
from app.prompt.prompt_loader import load_prompt


async def recall_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    step = "recall metric info"
    writer = runtime.stream_writer
    writer({"type":"progress", "step":step, "status":"running"})

    try:

        query = state["query"]
        keywords = state["keywords"]

        embedding_client = runtime.context["embedding_client"]
        metric_qdrant_repository = runtime.context["metric_qdrant_repository"]

        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_metric_recall"),
            input_variables=["query"],
        )
        output_parser = JsonOutputParser()

        chain = prompt | llm | output_parser

        result = await chain.ainvoke({"query": query})

        keywords = set(keywords + result)
        metric_info_map: dict[str, MetricInfo] = {}
        for keyword in keywords:
            # 指标库是向量集合，查询词必须先 Embedding 成 query vector
            embedding = await embedding_client.aembed_query(keyword)
            current_metric_infos: list[
                MetricInfo
            ] = await metric_qdrant_repository.search(embedding)
            for metric_info in current_metric_infos:
                if metric_info.id not in metric_info_map:
                    metric_info_map[metric_info.id] = metric_info

        # 写回 state 的是业务实体列表，后续过滤节点不需要关心 Qdrant 原始 point 结构
        retrieved_metric_infos: list[MetricInfo] = list(metric_info_map.values())
        logger.info(f"检索到指标信息：{list(metric_info_map.keys())}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"retrieved_metric_infos": retrieved_metric_infos}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise



