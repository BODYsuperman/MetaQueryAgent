import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime
from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.prompt.prompt_loader import load_prompt


async def rewrite_query(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """多轮追问改写：把依赖上下文的追问改写成自包含问题

    无历史（首轮或旧构造点）时直接跳过，不调用 LLM、不发进度事件。
    改写结果覆盖 state["query"] 供后续召回与生成使用；
    用户原话保存在 state["original_query"]，不受影响。
    """
    step = "Rewrite Query"
    writer = runtime.stream_writer

    # get 防御：graph.py __main__ 等旧构造点可能不带 history 键
    history = state.get("history") or []
    if not history:
        return {}

    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = state["query"]

        prompt = PromptTemplate(
            template=load_prompt("rewrite_query"),
            input_variables=["history", "query"],
        )
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        res = await chain.ainvoke(
            {
                # 与生成/校正节点一致，用 YAML 向模型提供结构化历史
                "history": yaml.dump(
                    history, allow_unicode=True, sort_keys=False
                ),
                "query": query,
            }
        )

        rewritten = res.strip()
        if not rewritten:
            # 模型输出异常（空/纯空白）时保留原问题，不把空串写进状态；
            # 没有发生改写就不发 success，避免前端误示"已改写"
            logger.warning("改写结果为空，保留原问题")
            return {}

        logger.info(f"改写后的问题：{rewritten}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"query": rewritten}
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
