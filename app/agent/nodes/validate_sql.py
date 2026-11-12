from langgraph.runtime import Runtime
from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.sql_safety import SqlSafetyError
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


async def validate_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    step = "Validate SQL"
    writer = runtime.stream_writer
    writer({"type":"progress", "step":step, "status":"running"})

    try:
        sql = state["sql"]
        dw_mysql_repository: DWMySQLRepository = runtime.context["dw_mysql_repository"]

        try:
            #use explain<sql> to confirm if mysql can decode this sql
            await  dw_mysql_repository.validate(sql)
            writer({"type": "progress", "step": step, "status": "success"})
            logger.info("SQL语法正确")
            return {"error": None}
        except SqlSafetyError as e:
            # 安全违规不走纠错流程，直接上抛终止图执行，前端收到 error 事件
            logger.error(f"SQL安全检查未通过：{e}")
            writer({"type": "progress", "step": step, "status": "error"})
            raise
        except Exception as e:
            # 不抛出异常中断图执行，而是把错误写入状态，供条件分支进入 correct_sql
            logger.info(f"SQL语法错误：{str(e)}")
            writer({"type": "progress", "step": step, "status": "success"})
            return {"error": str(e)}

    except SqlSafetyError:
        # 内层已记录日志并发出 error 事件，直接透传避免重复
        raise
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise



