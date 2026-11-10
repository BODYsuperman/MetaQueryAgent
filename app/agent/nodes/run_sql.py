from langgraph.runtime import Runtime
from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState



async def run_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    step = "Run SQL"
    writer = runtime.stream_writer
    writer({"type":"progress", "step":step, "status":"running"})

    try:
        sql = state["sql"]
        dw_mysql_repository = runtime.context["dw_mysql_repository"]

        # 真实数据库访问统一封装在仓储层，节点只负责从状态取 SQL 并触发执行
        result = await dw_mysql_repository.run(sql)
        logger.info(f"SQL执行结果：{result}")
        writer({"type": "progress", "step": step, "status": "success"})
        writer({"type": "result", "data": result})
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise



