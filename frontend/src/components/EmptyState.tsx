/**
 * 首页空状态组件
 * 展示产品入口信息和可点击的示例问数问题
 */
import { ArrowUpRight, BarChart3, LineChart, Search, ShoppingBag } from "lucide-react";

type EmptyStateProps = {
  examples: string[];
  onUseExample: (example: string) => void;
};

const highlights = [
  { label: "混合检索", icon: Search },
  { label: "SQL 闭环", icon: LineChart },
  { label: "电商数仓", icon: ShoppingBag },
];

export function EmptyState({ examples, onUseExample }: EmptyStateProps) {
  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-4 py-12">
      <div className="mb-8 flex flex-col items-center text-center">
        <div className="mb-4 grid h-14 w-14 place-items-center rounded-lg bg-primary-soft text-primary">
          <BarChart3 className="h-7 w-7" aria-hidden="true" />
        </div>
        <h1 className="text-[28px] font-semibold leading-tight">掌柜问数</h1>
        <p className="mt-2 text-sm text-muted">
          用自然语言查询电商数据仓库，自动生成并执行 SQL
        </p>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          {highlights.map((item) => {
            const Icon = item.icon;
            return (
              <span
                key={item.label}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted"
              >
                <Icon className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                {item.label}
              </span>
            );
          })}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onUseExample(example)}
            className="group rounded-lg border border-border bg-surface px-4 py-3.5 text-left text-[13px] leading-5 text-muted shadow-sm transition hover:-translate-y-0.5 hover:border-primary/40 hover:text-ink hover:shadow-md focus:outline-none focus:ring-2 focus:ring-primary/25"
          >
            <span className="block">{example}</span>
            <ArrowUpRight
              className="mt-2 h-4 w-4 text-faint transition group-hover:text-primary"
              aria-hidden="true"
            />
          </button>
        ))}
      </div>
    </div>
  );
}
