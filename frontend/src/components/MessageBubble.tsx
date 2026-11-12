/**
 * 聊天消息气泡组件
 * 组合展示用户问题、智能体回复、执行流程和结果表格
 */
import { Bot, Copy } from "lucide-react";
import { ResultTable } from "./ResultTable";
import { StepRail } from "./StepRail";
import { cn, formatTime, toClipboardText } from "../lib/format";
import type { ChatMessage } from "../types/agent";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  const copy = async () => {
    const text = message.result ? toClipboardText(message.result) : message.content;
    await navigator.clipboard.writeText(text);
  };

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%]">
          <div className="rounded-xl rounded-br-sm bg-primary-soft px-4 py-2.5 text-[14px] leading-6 text-ink">
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
          <div className="mt-1 pr-1 text-right text-[11px] text-faint">
            {formatTime(message.createdAt)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <article className="group flex gap-3">
      <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary text-white">
        <Bot className="h-4 w-4" aria-hidden="true" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="relative rounded-xl rounded-tl-sm border border-border bg-surface px-4 py-3 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <p className="whitespace-pre-wrap text-[14px] leading-6 text-ink">
              {message.content}
              {message.status === "streaming" && (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-primary align-text-bottom" />
              )}
            </p>
            {message.status !== "streaming" && (
              <button
                type="button"
                onClick={copy}
                className="shrink-0 rounded-md p-1.5 text-faint opacity-0 outline-none transition hover:bg-bg hover:text-ink focus:opacity-100 focus:ring-2 focus:ring-primary/30 group-hover:opacity-100"
                title="复制"
                aria-label="复制"
              >
                <Copy className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>

          {message.error && (
            <div className="mt-3 rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-[13px] leading-5 text-danger">
              {message.error}
            </div>
          )}

          <StepRail steps={message.steps} />
          {message.result !== undefined && <ResultTable data={message.result} />}
        </div>
        <div className="mt-1 pl-1 text-[11px] text-faint">
          {formatTime(message.createdAt)}
        </div>
      </div>
    </article>
  );
}
