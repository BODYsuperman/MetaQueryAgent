import jieba.analyse
from langgraph.runtime import Runtime
from loguru import logger

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState


async def extract_keywords(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    step = "extract key words"
    writer = runtime.stream_writer
    writer({"type": "progress", "step": step, "status": "running"})

    try:

        query = state["query"]
        # tuple allow_pos
        allow_pos = (
            "n",  # 名词: 商品、订单、销售额
            "nr",  # 人名: 张三、李四
            "ns",  # 地名: 华北、北京、上海
            "nt",  # 机构团体名: 门店、品牌、渠道
            "nz",  # 其他专有名词: SKU、GMV、AOV
            "v",  # 动词: 统计、对比、查询
            "vn",  # 名动词: 销售、成交、退款
            "a",  # 形容词: 新增、有效、活跃
            "an",  # 名形词: 可用、有效、异常
            "eng",  # 英文: GMV、SKU、ROI
            "i",  # 成语或习用语，避免遗漏整体表达
            "l",  # 常用固定短语，例如“销售总额”
        )
        keywords = jieba.analyse.extract_tags(query, topK=10, allowPOS=allow_pos)

        keywords = list(set(keywords + [query]))

        writer({"type": "progress", "step": step, "status": "success"})
        logger.info(f"extract key words successfully:{keywords}")

        return {"keywords": keywords}

    except Exception as e:
        logger.error(f"extract key words failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise



