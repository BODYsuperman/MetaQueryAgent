import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime
from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, MetricInfoState
from app.prompt.prompt_loader import load_prompt


async def filter_metric(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    step = "Filter Metric"
    writer = runtime.stream_writer
    writer({"type":"progress", "step":step, "status":"running"})

    try:

        query = state["query"]

        metric_infos: list[MetricInfoState] = state["metric_infos"]

        prompt = PromptTemplate(
            template= load_prompt("filter_metric_info"),
            input_variables= ["query", "metric_infos"]
        )

        output_parser = JsonOutputParser()
        #LCEL
        chain = prompt | llm | output_parser

        res = await chain.ainvoke(
            {
                "query": query,
                "metric_infos": yaml.dump(
                    metric_infos, allow_unicode=True, sort_keys=False
                ),
            }
        )

        filtered_metric_infos = [
            metric_info for metric_info in metric_infos if metric_info["name"] in res
        ]


        logger.info(
            f"过滤后的指标信息：{[filtered_metric_info['name'] for filtered_metric_info in filtered_metric_infos]}"
        )

        writer({"type": "progress", "step": step, "status": "success"})
        return {"metric_infos": filtered_metric_infos}


    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise



