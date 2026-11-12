/**
 * 查询结果表格组件
 * 将后端返回的结构化数据归一化为可滚动表格
 */
import { Database, Inbox } from "lucide-react";

function normalizeRows(data: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(data)) {
    return data.map((item, index) =>
      item && typeof item === "object" && !Array.isArray(item)
        ? (item as Record<string, unknown>)
        : { 序号: index + 1, 值: item },
    );
  }

  if (data && typeof data === "object") {
    return [data as Record<string, unknown>];
  }

  return [{ 值: data ?? "" }];
}

// 纯数字（含小数/负数）用于判断右对齐与千分位格式化
const NUMERIC = /^-?\d+(\.\d+)?$/;

const numberFormat = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 });

function isNumeric(value: unknown) {
  if (typeof value === "number") return Number.isFinite(value);
  return typeof value === "string" && NUMERIC.test(value.trim());
}

function formatCell(value: unknown) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number" && Number.isFinite(value)) {
    return numberFormat.format(value);
  }
  if (typeof value === "string" && NUMERIC.test(value.trim())) {
    return numberFormat.format(Number(value));
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function TableHeader({ rowCount }: { rowCount: number }) {
  return (
    <div className="flex items-center justify-between border-b border-border bg-bg/60 px-3.5 py-2.5">
      <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        <Database className="h-4 w-4 text-primary" aria-hidden="true" />
        查询结果
      </div>
      <span className="rounded-full bg-bg px-2 py-0.5 text-[11px] tabular-nums text-muted ring-1 ring-border">
        {rowCount} 行
      </span>
    </div>
  );
}

function EmptyBody() {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
      <Inbox className="h-6 w-6 text-faint" aria-hidden="true" />
      <div className="text-[13px] text-muted">查询完成，无匹配数据</div>
    </div>
  );
}

export function ResultTable({ data }: { data: unknown }) {
  // 空数组结果：展示空态而不是只剩表头的表格
  if (Array.isArray(data) && data.length === 0) {
    return (
      <section className="mt-3.5 overflow-hidden rounded-lg border border-border bg-surface">
        <TableHeader rowCount={0} />
        <EmptyBody />
      </section>
    );
  }

  const rows = normalizeRows(data);
  const columns = Array.from(
    rows.reduce((keys, row) => {
      Object.keys(row).forEach((key) => keys.add(key));
      return keys;
    }, new Set<string>()),
  );

  if (columns.length === 0) {
    return null;
  }

  // 按列判断是否为数值列（所有非空值都是数字），数值列右对齐
  const numericColumns = new Set(
    columns.filter((column) =>
      rows.every((row) => {
        const value = row[column];
        return value === null || value === undefined || isNumeric(value);
      }),
    ),
  );

  return (
    <section className="mt-3.5 overflow-hidden rounded-lg border border-border bg-surface">
      <TableHeader rowCount={rows.length} />
      <div className="max-h-[420px] overflow-auto">
        <table className="min-w-full border-separate border-spacing-0 text-left text-[13px]">
          <thead className="sticky top-0 z-10">
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className={
                    "border-b border-border bg-surface px-3.5 py-2.5 text-xs font-medium text-muted " +
                    (numericColumns.has(column) ? "text-right" : "")
                  }
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="even:bg-bg/40">
                {columns.map((column) => (
                  <td
                    key={column}
                    className={
                      "border-b border-border/60 px-3.5 py-2.5 text-ink/85 " +
                      (numericColumns.has(column) ? "text-right tabular-nums" : "")
                    }
                  >
                    {formatCell(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
