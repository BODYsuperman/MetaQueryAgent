from langgraph.runtime import Runtime
from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.services.session_store import session_store



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

        # 成功执行后写入会话历史，供后续追问改写参照；失败路径抛异常，不会写入
        session_id = state.get("session_id")
        if session_id:
            session_store.append(
                session_id,
                state.get("original_query") or state["query"],
                sql,
                result,
            )

        writer({"type": "progress", "step": step, "status": "success"})
        writer({"type": "result", "data": result})
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise



