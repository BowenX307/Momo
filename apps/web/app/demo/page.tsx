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
  fetchChatDemoStream,
  fetchHealth,
  MomoApiError,
  type ChatDemoRequest,
  type ChatDemoResponse,
  type HealthResponse,
  type HistoryMessage,
  type Persona,
  type Scene,
} from "@/lib/api/momo";
import {
  enqueueAudio,
  hadRealAudio,
  speakWithBrowser,
  stopAudioQueue,
  unlockAudio,
  whenQueueDone,
} from "@/lib/speech/playMomoSpeech";

import {
  clearSession,
  formatRelativeTime,
  loadSession,
  saveSession,
  type ConvTurn as PersistedConvTurn,
} from "@/lib/session/persistSession";

import { DebugDrawer } from "./_components/DebugDrawer";
import { PixelJellyfish } from "./_components/PixelJellyfish";
import { StatusHint } from "./_components/StatusHint";
import { ThinkingPhrases } from "./_components/ThinkingPhrases";
import {
  VoiceInputButton,
  type VoicePhase,
} from "./_components/VoiceInputButton";

const PERSONA_GREETINGS: Record<Persona, string> = {
  momo: "我在的。无论是哪种心情，都可以慢慢说，我会一直在。",
  iris: "来了？直接说吧，我在听。",
  rocky: "我在。你可以直接说，不用想怎么开口。",
};

const PERSONA_LABELS: Record<Persona, string> = {
  momo: "MOMO",
  iris: "Iris",
  rocky: "Rocky",
};
const MAX_HISTORY_DISPLAY = 3;

type ConvTurn = PersistedConvTurn;

export default function DemoPage() {
  // scene 由后端在第一句话上自动分类；此后整个会话都沿用，不再每轮重判。
  // null = 第一句话还没发过 / 用户尚未"开口定调"。
  const [scene, setScene] = useState<Scene | null>(null);
  const [persona, setPersona] = useState<Persona>("momo");
  const [input, setInput] = useState("");
  const [reply, setReply] = useState<string>(PERSONA_GREETINGS.momo);
  const [replyKey, setReplyKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [lastResponse, setLastResponse] = useState<ChatDemoResponse | null>(null);
  const [lastCurl, setLastCurl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [turns, setTurns] = useState<ConvTurn[]>([]);
  const [emotion, setEmotion] = useState<string>("");
  const [recordingTrigger, setRecordingTrigger] = useState(0);
  const [conversationActive, setConversationActive] = useState(false);
  const conversationActiveRef = useRef(false);
  const [restoredAt, setRestoredAt] = useState<number | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const historyEndRef = useRef<HTMLDivElement | null>(null);

  function handleStartConversation() {
    unlockAudio(); // must run inside user gesture to unblock iOS/Android autoplay
    conversationActiveRef.current = true;
    setConversationActive(true);
    setRecordingTrigger((t) => t + 1);
  }

  function handleEndConversation() {
    conversationActiveRef.current = false;
    setConversationActive(false);
    stopAudioQueue();
    setSpeaking(false);
    abortRef.current?.abort();
    setLoading(false);
  }

  function handleClearSession() {
    clearSession();
    setHistory([]);
    setScene(null);
    setTurns([]);
    setReply(PERSONA_GREETINGS[persona]);
    setReplyKey((k) => k + 1);
    setRestoredAt(null);
    setError(null);
    setEmotion("");
  }

  function handlePersonaChange(next: Persona) {
    if (next === persona) return;
    setPersona(next);
    clearSession();
    setHistory([]);
    setScene(null);
    setTurns([]);
    setReply(PERSONA_GREETINGS[next]);
    setReplyKey((k) => k + 1);
    setRestoredAt(null);
    setError(null);
    setEmotion("");
    stopAudioQueue();
    setSpeaking(false);
    abortRef.current?.abort();
    setLoading(false);
  }

  useEffect(() => {
    const saved = loadSession();
    if (saved) {
      setHistory(saved.history);
      setScene(saved.scene);
      setTurns(saved.turns);
      setRestoredAt(saved.savedAt);
      if (saved.turns.length > 0) {
        setReply(saved.turns[saved.turns.length - 1].reply);
      }
    }
    const ctrl = new AbortController();
    fetchHealth({ signal: ctrl.signal }).then(setHealth).catch(() => {});
    return () => {
      ctrl.abort();
      stopAudioQueue();
    };
  }, []);

  function applyReply(text: string) {
    setReply(text);
    setReplyKey((k) => k + 1);
  }

  async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;

    abortRef.current?.abort();
    stopAudioQueue();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    setInput("");
    setEmotion("");
    const payload: ChatDemoRequest = scene
      ? { user_text: text, scene, persona, history }
      : { user_text: text, persona, history };
    setLastCurl(buildCurl(payload, API_BASE));

    // Capture state values for use inside callbacks (React closure safety).
    const capturedHistory = history;
    const capturedTurns = turns;
    const capturedScene = scene;

    try {
      await fetchChatDemoStream(
        payload,
        {
          onAudio: (ev) => {
            enqueueAudio(ev.audio_base64, ev.content_type, ev.is_mock);
          },
          onDone: (ev) => {
            if (ctrl.signal.aborted) return;

            applyReply(ev.reply);
            if (ev.scene !== capturedScene) setScene(ev.scene);
            if (ev.emotion) setEmotion(ev.emotion);

            const nextHistory: HistoryMessage[] = [
              ...capturedHistory,
              { role: "user" as const, content: text },
              { role: "assistant" as const, content: ev.reply },
            ].slice(-20);
            setHistory(nextHistory);

            const nextTurns = [...capturedTurns, { userText: text, reply: ev.reply }];
            setTurns(nextTurns);
            saveSession({ history: nextHistory, scene: ev.scene, turns: nextTurns, savedAt: Date.now() });
            setRestoredAt(null);

            setLastResponse({
              reply: ev.reply,
              scene: ev.scene,
              safety_flag: ev.safety_flag,
              is_mock: ev.is_mock,
              request_id: ev.request_id,
              degraded: ev.degraded,
              audio_base64: "",
              audio_content_type: "audio/mpeg",
              audio_is_mock: !hadRealAudio(),
            } satisfies ChatDemoResponse);

            setLoading(false);
            setSpeaking(true);

            const afterSpeak = () => {
              if (!ctrl.signal.aborted) {
                setSpeaking(false);
                if (conversationActiveRef.current) {
                  setRecordingTrigger((t) => t + 1);
                }
              }
            };

            if (hadRealAudio()) {
              void whenQueueDone().then(afterSpeak);
            } else {
              void speakWithBrowser(ev.reply).then(afterSpeak).catch(afterSpeak);
            }
          },
        },
        { signal: ctrl.signal },
      );
      // If onDone was never called (empty stream), clean up loading.
      if (!ctrl.signal.aborted) setLoading(false);
    } catch (err) {
      if (ctrl.signal.aborted) return;
      const msg =
        err instanceof MomoApiError
          ? `连接后端失败（${err.status ?? "网络"}）`
          : err instanceof Error
            ? err.message
            : "未知错误";
      setError(msg);
      setLoading(false);
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

      <header className="flex items-start justify-between px-6 pt-6 sm:px-10 sm:pt-10">
        <div>
          <h1 className="text-lg font-medium tracking-tight">{PERSONA_LABELS[persona]}</h1>
          <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
            {persona === "momo" ? "我一直在。" : persona === "iris" ? "有什么就说。" : "先把问题变小。"}
          </p>
        </div>
        <div className="flex gap-1 rounded-xl bg-stone-100 p-1 dark:bg-stone-800">
          {(["momo", "iris", "rocky"] as Persona[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => handlePersonaChange(p)}
              className={`rounded-lg px-3 py-1 text-sm font-medium transition-colors ${
                persona === p
                  ? "bg-white text-stone-900 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                  : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
              }`}
            >
              {PERSONA_LABELS[p]}
            </button>
          ))}
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 pb-10 sm:px-10">
        <PixelJellyfish thinking={loading || speaking} degraded={degraded} size={192} />

        {/* 情绪标签：用户说完后展示检测到的情绪 */}
        {emotion && !loading && (
          <div
            className="flex items-center gap-1.5 rounded-full bg-stone-100 px-3.5 py-1 dark:bg-stone-800"
            style={{ animation: "momo-fade-in 380ms ease-out both" }}
          >
            <span className="text-xs text-stone-400 dark:text-stone-500">感受到了</span>
            <span className="text-sm font-medium text-stone-600 dark:text-stone-300">{emotion}</span>
          </div>
        )}

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
            {loading ? (
              <ThinkingPhrases variant="thinking" />
            ) : voicePhase === "transcribing" ? (
              <ThinkingPhrases variant="transcribing" />
            ) : voicePhase === "recording" ? (
              <span className="text-stone-400">我在听…</span>
            ) : (
              reply
            )}
          </p>
          <StatusHint safetyFlag={safetyFlag} degraded={degraded} error={error} />
        </div>

        {/* 会话恢复提示 */}
        {restoredAt !== null && (
          <div className="flex w-full max-w-md items-center justify-between text-xs text-stone-400 dark:text-stone-500">
            <span>上次聊到这里 · {formatRelativeTime(restoredAt)}</span>
            <button
              type="button"
              onClick={handleClearSession}
              className="rounded px-2 py-0.5 hover:text-stone-600 dark:hover:text-stone-300"
            >
              重新开始
            </button>
          </div>
        )}

        {/* 输入框：scene 由后端自动分类，用户不再选 */}
        <div className="w-full max-w-md">
          <div className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-white/70 p-2 focus-within:border-[#e88c6a] focus-within:bg-white dark:border-stone-800 dark:bg-stone-900/60 dark:focus-within:border-[#c66645] dark:focus-within:bg-stone-900">
            <VoiceInputButton
              disabled={loading || speaking}
              startTrigger={recordingTrigger}
              conversationActive={conversationActive}
              onStartConversation={handleStartConversation}
              onEndConversation={handleEndConversation}
              onPhaseChange={setVoicePhase}
              onTranscript={(text) => void handleSend(text)}
              onError={setError}
            />
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="说点什么，或点左边麦克风…"
              rows={1}
              disabled={loading || speaking}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-base leading-relaxed text-stone-900 placeholder-stone-400 outline-none disabled:opacity-60 dark:text-stone-100 dark:placeholder-stone-500"
            />
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={loading || speaking || !input.trim()}
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
