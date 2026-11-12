"""
SQL 安全防护

对 LLM 生成、面向数仓执行的 SQL 做四层防护中的前两层：
1. 只读限制：sqlglot AST 解析，必须恰好一条 SELECT（含 WITH/UNION）语句
2. 黑名单关键字：词边界正则扫描原始文本，作为第二层防御

仓储层（DWMySQLRepository.validate/run）统一调用本模块，
任何执行路径都无法绕过。超时与行数截断在仓储层实现，
行数改写由 apply_row_limit 提供。
"""

import re

import sqlglot
from sqlglot import exp

from app.conf.app_config import SqlSafetyConfig, app_config


class SqlSafetyError(Exception):
    """SQL 安全违规专用异常，抛出后直接终止本次查询"""


# 只允许这些 AST 语句类型通过（只读查询，含 UNION/EXCEPT/INTERSECT 组合）
_ALLOWED_STATEMENT_TYPES = (exp.Select, exp.Union, exp.Except, exp.Intersect)


class SqlSafetyChecker:

    def __init__(self, config: SqlSafetyConfig):
        self.config = config
        # 名单为空时不做黑名单扫描
        if config.blacklisted_keywords:
            self._blacklist_pattern = re.compile(
                r"\b(" + "|".join(config.blacklisted_keywords) + r")\b",
                re.IGNORECASE,
            )
        else:
            self._blacklist_pattern = None

    def check(self, sql: str) -> None:
        """只读校验 + 黑名单扫描，违规抛 SqlSafetyError

        语法解析失败时原样上抛 sqlglot 的 ParseError，
        交回 validate_sql/correct_sql 的语法纠错流程处理
        """
        if not self.config.enabled:
            return

        # 黑名单先于 AST 解析：sqlglot 解析不了的语句（如 INTO OUTFILE）
        # 也必须被黑名单拦截，而不是降级成 ParseError 走语法纠错流程
        if self._blacklist_pattern:
            match = self._blacklist_pattern.search(sql)
            if match:
                raise SqlSafetyError(
                    f"SQL包含被禁止的关键字: {match.group(1).upper()}"
                )

        expressions = [
            e for e in sqlglot.parse(sql, dialect="mysql") if e is not None
        ]
        if len(expressions) != 1:
            raise SqlSafetyError("只允许执行单条SQL语句")

        if not isinstance(expressions[0], _ALLOWED_STATEMENT_TYPES):
            raise SqlSafetyError("只允许执行只读SELECT查询")

    def apply_row_limit(self, sql: str) -> str:
        """改写 SQL 的 LIMIT，保证返回行数不超过 max_rows

        无 LIMIT 则追加；已有 LIMIT 超过 max_rows 则收紧；
        已有 LIMIT 不超过 max_rows 时保留原值
        """
        if not self.config.enabled:
            return sql

        expression = sqlglot.parse_one(sql, dialect="mysql")
        limit = expression.args.get("limit")
        if limit is not None:
            try:
                # LIMIT 字面量时比较大小，非字面量（如占位符）按超限处理
                current = int(limit.expression.this)
            except (AttributeError, TypeError, ValueError):
                current = None
            if current is not None and current <= self.config.max_rows:
                return sql

        return expression.limit(self.config.max_rows, dialect="mysql").sql(
            dialect="mysql"
        )


# 模块级单例，与项目现有 client_manager 的使用模式保持一致
sql_safety_checker = SqlSafetyChecker(app_config.sql_safety)
