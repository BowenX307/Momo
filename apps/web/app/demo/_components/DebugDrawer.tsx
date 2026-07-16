"use client";

/**
 * 右下角小齿轮 → 调试抽屉。
 *
 * 给非技术听众看时折叠状态完全隐形；技术听众点开能拿到：
 * - 当前 provider（绿点 deepseek / 灰点 mock / ? 未知）
 * - 最近一次响应的完整 JSON
 * - request_id（一键复制，方便对后端日志）
 * - 等价 curl 命令文本（一键复制，给前端/工程师演示）
 * - API base 地址（只显示，不可改 —— 改要走 .env.local + 重启 next dev）
 */

import { useEffect, useRef, useState } from "react";

import type { ChatDemoResponse, HealthResponse } from "@/lib/api/yewne";

interface Props {
  apiBase: string;
  health: HealthResponse | null;
  lastResponse: ChatDemoResponse | null;
  lastCurl: string | null;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          // ignore: clipboard 不可用时按钮静默失败，演示场景下基本不会发生
        }
      }}
      className="rounded border border-stone-300 bg-white px-2 py-0.5 text-[11px] text-stone-600 transition-colors hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400 dark:hover:bg-stone-800"
    >
      {copied ? "已复制" : label}
    </button>
  );
}

function ProviderBadge({ health }: { health: HealthResponse | null }) {
  if (!health) {
    return (
      <span className="inline-flex items-center gap-1.5 text-stone-500">
        <span className="h-2 w-2 rounded-full bg-stone-400" />
        provider 未知（后端未连上）
      </span>
    );
  }
  const isReal = !health.llm_is_mock;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`h-2 w-2 rounded-full ${isReal ? "bg-emerald-500" : "bg-stone-400"}`}
      />
      <span className="text-stone-700 dark:text-stone-300">
        provider: <code>{health.llm_provider}</code>
      </span>
      <span className="text-stone-500">{isReal ? "（真模型）" : "（mock）"}</span>
    </span>
  );
}

export function DebugDrawer({ apiBase, health, lastResponse, lastCurl }: Props) {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        aria-label="调试面板"
        onClick={() => setOpen((v) => !v)}
        className="fixed right-4 bottom-4 z-40 inline-flex h-9 w-9 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-500 shadow-sm transition-colors hover:bg-stone-50 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-400 dark:hover:bg-stone-800"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px]"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            ref={dialogRef}
            role="dialog"
            aria-label="调试面板"
            className="fixed right-0 top-0 bottom-0 z-50 flex w-full max-w-sm flex-col gap-4 overflow-y-auto border-l border-stone-200 bg-white p-5 shadow-xl dark:border-stone-800 dark:bg-stone-950"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-stone-700 dark:text-stone-200">
                调试面板
              </h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-xs text-stone-500 hover:text-stone-800 dark:hover:text-stone-200"
              >
                关闭
              </button>
            </div>

            <section className="space-y-1.5 text-xs">
              <div className="text-[11px] uppercase tracking-wide text-stone-400">
                后端连接
              </div>
              <ProviderBadge health={health} />
              <div className="text-stone-500">
                API base: <code className="text-stone-700 dark:text-stone-300">{apiBase}</code>
              </div>
              <div className="text-[11px] text-stone-400">
                修改地址请编辑 <code>apps/web/.env.local</code> 后重启 dev server。
              </div>
            </section>

            <section className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <div className="text-[11px] uppercase tracking-wide text-stone-400">
                  最近一次响应
                </div>
                {lastResponse && (
                  <CopyButton
                    text={JSON.stringify(lastResponse, null, 2)}
                    label="复制 JSON"
                  />
                )}
              </div>
              {lastResponse ? (
                <pre className="max-h-72 overflow-auto rounded bg-stone-50 p-2 text-[11px] leading-relaxed text-stone-700 dark:bg-stone-900 dark:text-stone-300">
                  {JSON.stringify(lastResponse, null, 2)}
                </pre>
              ) : (
                <p className="text-stone-400">还没有请求过。</p>
              )}
              {lastResponse && (
                <div className="flex items-center justify-between text-[11px] text-stone-500">
                  <span>
                    request_id:{" "}
                    <code className="text-stone-700 dark:text-stone-300">
                      {lastResponse.request_id}
                    </code>
                  </span>
                  <CopyButton text={lastResponse.request_id} label="复制 id" />
                </div>
              )}
            </section>

            {lastCurl && (
              <section className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <div className="text-[11px] uppercase tracking-wide text-stone-400">
                    等价 curl
                  </div>
                  <CopyButton text={lastCurl} label="复制 curl" />
                </div>
                <pre className="overflow-auto rounded bg-stone-50 p-2 text-[11px] leading-relaxed text-stone-700 dark:bg-stone-900 dark:text-stone-300">
                  {lastCurl}
                </pre>
              </section>
            )}
          </div>
        </>
      )}
    </>
  );
}
