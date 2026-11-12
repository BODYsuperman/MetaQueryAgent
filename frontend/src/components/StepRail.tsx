/**
 * 智能体执行流程组件
 * 可折叠的纵向步骤列表；step 键与后端各节点发出的 progress 事件字符串逐字一致
 */
import { Check, ChevronDown, Circle, LoaderCircle, X } from "lucide-react";
import { useState } from "react";
import { cn } from "../lib/format";
import type { ProgressStatus, StepState } from "../types/agent";

type FlowStatus = ProgressStatus | "pending";

// key 必须与后端 app/agent/nodes/*.py 中 step = "..." 逐字一致（含空格与中文）
const FLOW_STEPS: Array<{ key: string; label: string; note?: string }> = [
  { key: "Rewrite Query", label: "问题改写", note: "多轮追问时执行" },
  { key: "extract key words", label: "关键词抽取" },
  { key: "recall column info", label: "字段召回" },
  { key: "recall metric info", label: "指标召回" },
  { key: "recall value", label: "取值召回" },
  { key: "Merge retrieved info", label: "信息合并" },
  { key: "Filter Metric", label: "指标过滤" },
  { key: "Filter Table", label: "表过滤" },
  { key: "添加额外上下文", label: "补充上下文" },
  { key: "Generate SQL", label: "生成 SQL" },
  { key: "Validate SQL", label: "校验 SQL" },
  { key: "校正SQL", label: "校正 SQL", note: "仅校验失败时执行" },
  { key: "Run SQL", label: "执行查询" },
];

function getStatusMap(steps: StepState[]) {
  return steps.reduce<Record<string, StepState>>((map, item) => {
    map[item.step] = item;
    return map;
  }, {});
}

function StepIcon({ status }: { status: FlowStatus }) {
  if (status === "running") {
    return <LoaderCircle className="h-3.5 w-3.5 animate-spin text-info" aria-hidden="true" />;
  }
  if (status === "success") {
    return <Check className="h-3.5 w-3.5 text-success" aria-hidden="true" />;
  }
  if (status === "error") {
    return <X className="h-3.5 w-3.5 text-danger" aria-hidden="true" />;
  }
  return <Circle className="h-3.5 w-3.5 text-faint/50" aria-hidden="true" />;
}

export function StepRail({ steps = [] }: { steps?: StepState[] }) {
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0) return null;

  const statusMap = getStatusMap(steps);
  const finished = FLOW_STEPS.filter((item) => {
    const status = statusMap[item.key]?.status;
    return status === "success" || status === "error";
  }).length;
  const progress = Math.round((finished / FLOW_STEPS.length) * 100);

  return (
    <section className="mt-3.5 overflow-hidden rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left transition hover:bg-bg/60"
        aria-expanded={expanded}
      >
        <span className="flex min-w-0 items-center gap-2 text-[13px] font-semibold text-ink">
          执行流程
          <span className="rounded-full bg-bg px-2 py-0.5 text-[11px] font-normal tabular-nums text-muted ring-1 ring-border">
            {finished}/{FLOW_STEPS.length}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="hidden h-1 w-24 overflow-hidden rounded-full bg-border sm:block">
            <span
              className="block h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-faint transition-transform duration-200",
              expanded && "rotate-180",
            )}
            aria-hidden="true"
          />
        </span>
      </button>

      {expanded && (
        <ul className="divide-y divide-border/70 border-t border-border">
          {FLOW_STEPS.map((item) => {
            // 显式标注可空：否则索引访问被 TS 视为必然存在，?? "pending" 会被当作死代码
            const stepState: StepState | undefined = statusMap[item.key];
            const status: FlowStatus = stepState ? stepState.status : "pending";
            const isPending = !stepState;
            return (
              <li
                key={item.key}
                className="flex items-center gap-2.5 px-3.5 py-2"
              >
                <StepIcon status={status} />
                <span
                  className={cn(
                    "text-[13px]",
                    isPending ? "text-faint" : "text-ink",
                  )}
                >
                  {item.label}
                  {item.note && (
                    <span className="ml-1.5 text-[11px] text-faint">（{item.note}）</span>
                  )}
                </span>
                <span className="ml-auto hidden truncate font-mono text-[11px] text-faint md:block">
                  {item.key}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
