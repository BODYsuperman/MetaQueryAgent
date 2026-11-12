/**
 * 聊天输入区组件
 * 处理问题输入、发送和停止当前流式请求
 */
import { ArrowUp, Square } from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useRef } from "react";
import { cn } from "../lib/format";

type ComposerProps = {
    value: string;
    disabled: boolean;
    isStreaming: boolean;
    onChange: (value: string) => void;
    onSubmit: () => void;
    onStop: () => void;
};

// textarea 最多长到 8 行，超过后内部滚动
const MAX_HEIGHT = 8 * 24;

export function Composer({
    value,
    disabled,
    isStreaming,
    onChange,
    onSubmit,
    onStop,
}: ComposerProps) {
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    // 内容变化时自动增高；清空后恢复单行
    useEffect(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
    }, [value]);

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (!disabled) onSubmit();
    };

    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!disabled) onSubmit();
        }
    };

    return (
        <form
            onSubmit={submit}
            className="border-t border-border bg-surface px-4 py-3.5"
        >
            <div className="mx-auto max-w-3xl">
                <div className="flex items-end gap-2 rounded-xl border border-border bg-surface p-2 transition focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15">
                    <textarea
                        ref={textareaRef}
                        value={value}
                        onChange={(event) => onChange(event.target.value)}
                        onKeyDown={onKeyDown}
                        rows={1}
                        placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
                        className="max-h-48 min-h-10 flex-1 resize-none bg-transparent px-2 py-2.5 text-[14px] leading-6 text-ink outline-none placeholder:text-faint"
                    />
                    <button
                        type={isStreaming ? "button" : "submit"}
                        onClick={isStreaming ? onStop : undefined}
                        disabled={!isStreaming && disabled}
                        className={cn(
                            "grid h-9 w-9 shrink-0 place-items-center rounded-lg text-white transition focus:outline-none focus:ring-2 focus:ring-primary/30 focus:ring-offset-1",
                            isStreaming
                                ? "bg-danger hover:bg-danger/90"
                                : "bg-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-border disabled:text-faint",
                        )}
                        title={isStreaming ? "停止" : "发送"}
                        aria-label={isStreaming ? "停止" : "发送"}
                    >
                        {isStreaming ? (
                            <Square
                                className="h-3.5 w-3.5 fill-current"
                                aria-hidden="true"
                            />
                        ) : (
                            <ArrowUp className="h-4 w-4" aria-hidden="true" />
                        )}
                    </button>
                </div>
            </div>
        </form>
    );
}
