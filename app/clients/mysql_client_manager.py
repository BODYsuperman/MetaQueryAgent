from typing import Optional

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine, AsyncSession,
)


from app.conf.app_config import DBConfig, app_config


class MySQLClientManager:

    def __init__(self, config: DBConfig):
        self.engine:Optional[AsyncEngine] = None

        self.session_factory:Optional[async_sessionmaker] = None

        self.config = config

    def _get_url(self):
        return f"mysql+asyncmy://{self.config.user}:{self.config.password}@{self.config.host}:{self.config.port}/{self.config.database}?charset=utf8mb4"

    def init(self):
        self.engine = create_async_engine(
            url= self._get_url(),
            echo = True,
            pool_size=10,
            pool_pre_ping=True
        )

        self.session_factory = async_sessionmaker(
            bind = self.engine,
            autoflush=True,
            expire_on_commit=False
        )


    async def close(self):
        if self.engine:
            await self.engine.dispose()


dw_mysql_client_manager = MySQLClientManager(app_config.db_dw)
meta_mysql_client_manager = MySQLClientManager(app_config.db_meta)

if __name__ == "__main__":
    dw_mysql_client_manager.init()

    async def test():
        """执行一次简单查询，验证 MySQL 连接与结果结构"""
        async with dw_mysql_client_manager.session_factory() as session:
            sql = "select * from fact_order limit 10"
            result = await session.execute(text(sql))
            # mappings().fetchall() 会把结果转成“按列名访问”的行对象列表
            rows = result.mappings().fetchall()


            print(type(rows))
            print(type(rows[0]))
            print(rows[0]["order_id"])

    asyncio.run(test())
