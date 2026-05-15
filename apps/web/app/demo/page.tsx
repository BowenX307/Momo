"use client";

/**
 * /demo —— MOMO 陪伴体的最小可演示页面。
 *
 * 设计目标：
 * - 不是 chat box。屏幕中心是一个像素小水母（陪伴体），它"在那里"，
 *   你输入一句话，它给一句回应；新一句替换旧一句（淡入淡出），
 *   而不是堆叠成对话流。
 * - 场景选择放在底部，措辞用第一人称，更柔和。
 * - 危机/降级/错误状态用回复下方一行小字表达，不弹窗。
 * - 调试细节统统藏进右下角齿轮。
 */

import { useEffect, useRef, useState } from "react";

import {
  API_BASE,
  buildCurl,
  fetchChatDemo,
  fetchHealth,
  MomoApiError,
  type ChatDemoResponse,
  type HealthResponse,
  type Scene,
} from "@/lib/api/momo";

import { DebugDrawer } from "./_components/DebugDrawer";
import { PixelJellyfish } from "./_components/PixelJellyfish";
import { SceneSelector } from "./_components/SceneSelector";
import { StatusHint } from "./_components/StatusHint";

const INITIAL_GREETING =
  "我在的。无论是哪种心情，都可以慢慢说，我会一直在。";

export default function DemoPage() {
  const [scene, setScene] = useState<Scene>("loneliness");
  const [input, setInput] = useState("");
  const [reply, setReply] = useState<string>(INITIAL_GREETING);
  const [replyKey, setReplyKey] = useState(0); // 用来触发淡入动画
  const [loading, setLoading] = useState(false);
  const [lastResponse, setLastResponse] = useState<ChatDemoResponse | null>(null);
  const [lastCurl, setLastCurl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  // 启动时拉一次 /health 拿 provider 状态。失败时 health 仍为 null，
  // 调试面板会显示"未知 / 后端未连上"，主体功能不阻塞。
  useEffect(() => {
    const ctrl = new AbortController();
    fetchHealth({ signal: ctrl.signal }).then(setHealth).catch(() => {});
    return () => ctrl.abort();
  }, []);

  function applyReply(text: string) {
    setReply(text);
    setReplyKey((k) => k + 1);
  }

  async function handleSend() {
    const text = input;
    if (!text.trim() || loading) return;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    const payload = { user_text: text, scene };
    setLastCurl(buildCurl(payload, API_BASE));

    try {
      const res = await fetchChatDemo(payload, { signal: ctrl.signal });
      setLastResponse(res);
      applyReply(res.reply);
      setInput("");
    } catch (err) {
      if (ctrl.signal.aborted) return;
      const msg =
        err instanceof MomoApiError
          ? `连接后端失败（${err.status ?? "网络"}）`
          : err instanceof Error
            ? err.message
            : "未知错误";
      setError(msg);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter 发送，Shift+Enter 换行；移动端长按拼音不会触发 Enter
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  }

  const safetyFlag = lastResponse?.safety_flag;
  const degraded = lastResponse?.degraded ?? false;

  return (
    <div className="relative flex min-h-dvh flex-1 flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <style>{`
        @keyframes momo-fade-in {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes momo-tentacle-think {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
      `}</style>

      <header className="px-6 pt-6 sm:px-10 sm:pt-10">
        <h1 className="text-lg font-medium tracking-tight">Momo</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">我一直在。</p>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-8 px-6 pb-10 sm:px-10">
        <PixelJellyfish thinking={loading} degraded={degraded} />

        <div className="flex w-full max-w-md flex-col items-center">
          <p
            key={replyKey}
            className="min-h-[3em] text-center text-base leading-relaxed text-zinc-800 sm:text-lg dark:text-zinc-100"
            style={{ animation: "momo-fade-in 420ms ease-out both" }}
          >
            {loading ? <ThinkingDots /> : reply}
          </p>
          <StatusHint safetyFlag={safetyFlag} degraded={degraded} error={error} />
        </div>

        <div className="w-full max-w-md">
          <div className="flex items-end gap-2 rounded-2xl border border-zinc-200 bg-white p-2 shadow-sm focus-within:border-violet-300 focus-within:ring-2 focus-within:ring-violet-100 dark:border-zinc-800 dark:bg-zinc-900 dark:focus-within:border-violet-600 dark:focus-within:ring-violet-950">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="说点什么…（Enter 发送，Shift+Enter 换行）"
              rows={1}
              disabled={loading}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-base leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none disabled:opacity-60 dark:text-zinc-100 dark:placeholder-zinc-500"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="shrink-0 rounded-xl bg-violet-500 px-3.5 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-violet-600 disabled:cursor-not-allowed disabled:bg-zinc-300 dark:disabled:bg-zinc-700"
            >
              {loading ? "等一下" : "发送"}
            </button>
          </div>
        </div>

        <div className="w-full max-w-md pt-2">
          <SceneSelector value={scene} onChange={setScene} disabled={loading} />
        </div>
      </main>

      <DebugDrawer
        apiBase={API_BASE}
        health={health}
        lastResponse={lastResponse}
        lastCurl={lastCurl}
      />
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-end gap-1 text-zinc-400">
      <Dot delay="0s" />
      <Dot delay="0.18s" />
      <Dot delay="0.36s" />
    </span>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 rounded-full bg-current"
      style={{
        animation: "momo-tentacle-think 1.1s ease-in-out infinite",
        animationDelay: delay,
      }}
    />
  );
}
