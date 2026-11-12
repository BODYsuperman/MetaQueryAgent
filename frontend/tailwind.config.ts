/**
 * Tailwind CSS 主题配置
 * 设计令牌统一在此定义：语义化颜色、圆角、阴影与字体栈
 */
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          '"PingFang SC"',
          '"Noto Sans SC"',
          '"Microsoft YaHei"',
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          '"SF Mono"',
          '"JetBrains Mono"',
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        // 品牌色（墨绿）
        primary: {
          DEFAULT: "#1a7f4e",
          hover: "#15683f",
          soft: "#f0f7f3",
        },
        // 表面与结构
        bg: "#f7f8f8",
        surface: "#ffffff",
        border: "#e4e7e6",
        // 文字层级
        ink: "#16191a",
        muted: "#5c6461",
        // 对比度满足 WCAG AA（白底 ≈4.6:1）；原 #8b938f 仅 3.1:1
        faint: "#6b7470",
        // 语义色
        success: "#1a7f4e",
        warning: "#b4761a",
        danger: "#c43d2b",
        info: "#2563eb",
      },
      borderRadius: {
        DEFAULT: "8px",
        lg: "12px",
      },
      boxShadow: {
        sm: "0 1px 2px rgba(16, 24, 20, 0.05)",
        md: "0 4px 16px rgba(16, 24, 20, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
