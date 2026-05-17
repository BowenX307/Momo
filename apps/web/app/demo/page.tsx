"use client";

/**
 * /demo —— MOMO 陪伴体的最小可演示页面。
 *
 * 设计目标：
 * - 不是 chat box。屏幕中心是一个像素小水母（陪伴体），它"在那里"。
 * - 最新的 MOMO 回复是焦点（大字居中），之前几轮以小气泡形式保留在上方。
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
  type ChatDemoRequest,
  type ChatDemoResponse,
  type HealthResponse,
  type HistoryMessage,
  type Scene,
} from "@/lib/api/momo";

import { DebugDrawer } from "./_components/DebugDrawer";
import { PixelJellyfish } from "./_components/PixelJellyfish";
import { StatusHint } from "./_components/StatusHint";

const INITIAL_GREETING = "我在的。无论是哪种心情，都可以慢慢说，我会一直在。";
const MAX_HISTORY_DISPLAY = 3; // 最多展示几条历史气泡

interface ConvTurn {
  userText: string;
  reply: string;
}

export default function DemoPage() {
  // scene 由后端在第一句话上自动分类；此后整个会话都沿用，不再每轮重判。
  // null = 第一句话还没发过 / 用户尚未"开口定调"。
  const [scene, setScene] = useState<Scene | null>(null);
  const [input, setInput] = useState("");
  const [reply, setReply] = useState<string>(INITIAL_GREETING);
  const [replyKey, setReplyKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [lastResponse, setLastResponse] = useState<ChatDemoResponse | null>(null);
  const [lastCurl, setLastCurl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [turns, setTurns] = useState<ConvTurn[]>([]);

  const abortRef = useRef<AbortController | null>(null);
  const historyEndRef = useRef<HTMLDivElement | null>(null);

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
    const text = input.trim();
    if (!text || loading) return;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    // 第一句话不传 scene → 后端自动分类；后续把已锁定的 scene 传回，避免重复分类。
    const payload: ChatDemoRequest = scene
      ? { user_text: text, scene, history }
      : { user_text: text, history };
    setLastCurl(buildCurl(payload, API_BASE));

    try {
      const res = await fetchChatDemo(payload, { signal: ctrl.signal });
      setLastResponse(res);
      applyReply(res.reply);
      setInput("");
      // 锁定本会话场景：后端可能是从分类得来，也可能就是我们传上去的，统一以响应为准。
      if (res.scene !== scene) setScene(res.scene);

      const nextHistory: HistoryMessage[] = [
        ...history,
        { role: "user" as const, content: text },
        { role: "assistant" as const, content: res.reply },
      ].slice(-20);
      setHistory(nextHistory);

      setTurns((prev) => [...prev, { userText: text, reply: res.reply }]);
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
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  }

  const safetyFlag = lastResponse?.safety_flag;
  const degraded = lastResponse?.degraded ?? false;

  // 最近几轮（不含当前回复）
  const recentTurns = turns.slice(-(MAX_HISTORY_DISPLAY + 1), -1);

  return (
    <div className="relative flex min-h-dvh flex-1 flex-col bg-[#faf6f0] text-stone-900 dark:bg-[#1a1612] dark:text-stone-100">
      <style>{`
        @keyframes momo-fade-in {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes momo-fade-up {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 0.55; transform: translateY(0); }
        }
        @keyframes momo-tentacle-think {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
        .momo-history-turn {
          animation: momo-fade-up 380ms ease-out both;
        }
      `}</style>

      <header className="px-6 pt-6 sm:px-10 sm:pt-10">
        <h1 className="text-lg font-medium tracking-tight">Momo</h1>
        <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">我一直在。</p>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 pb-10 sm:px-10">
        <PixelJellyfish thinking={loading} degraded={degraded} size={192} />

        {/* 历史气泡区：最近几轮对话，小字 + 半透明 */}
        {recentTurns.length > 0 && (
          <div className="flex w-full max-w-md flex-col gap-3">
            {recentTurns.map((turn, i) => (
              <div key={i} className="momo-history-turn flex flex-col gap-1 opacity-55">
                <div className="flex justify-end">
                  <span className="max-w-[80%] rounded-2xl rounded-br-sm bg-[#e8e2da] px-3 py-1.5 text-xs leading-relaxed text-stone-600 dark:bg-stone-800 dark:text-stone-400">
                    {turn.userText}
                  </span>
                </div>
                <div className="flex justify-start">
                  <span className="max-w-[80%] rounded-2xl rounded-bl-sm bg-[#f0ebe4] px-3 py-1.5 text-xs leading-relaxed text-stone-500 dark:bg-stone-900 dark:text-stone-500">
                    {turn.reply}
                  </span>
                </div>
              </div>
            ))}
            <div ref={historyEndRef} />
          </div>
        )}

        {/* 当前回复：主视觉焦点 */}
        <div className="flex w-full max-w-md flex-col items-center">
          <p
            key={replyKey}
            className="min-h-[3em] text-center text-base leading-relaxed text-stone-800 sm:text-lg dark:text-stone-100"
            style={{ animation: "momo-fade-in 420ms ease-out both" }}
          >
            {loading ? <ThinkingDots /> : reply}
          </p>
          <StatusHint safetyFlag={safetyFlag} degraded={degraded} error={error} />
        </div>

        {/* 输入框：scene 由后端自动分类，用户不再选 */}
        <div className="w-full max-w-md">
          <div className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-white/70 p-2 focus-within:border-[#e88c6a] focus-within:bg-white dark:border-stone-800 dark:bg-stone-900/60 dark:focus-within:border-[#c66645] dark:focus-within:bg-stone-900">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="说点什么…（Enter 发送，Shift+Enter 换行）"
              rows={1}
              disabled={loading}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-base leading-relaxed text-stone-900 placeholder-stone-400 outline-none disabled:opacity-60 dark:text-stone-100 dark:placeholder-stone-500"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="shrink-0 rounded-xl bg-[#d97757] px-3.5 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[#c66645] disabled:cursor-not-allowed disabled:bg-stone-300 dark:disabled:bg-stone-700"
            >
              {loading ? "等一下" : "发送"}
            </button>
          </div>
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
    <span className="inline-flex items-end gap-1 text-stone-400">
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
