"use client";

/**
 * /demo —— 于你陪伴体的最小可演示页面。
 *
 * 设计目标：
 * - 不是 chat box。屏幕中心是一个像素小水母（陪伴体），它"在那里"。
 * - 最新的于你回复是焦点（大字居中），之前几轮以小气泡形式保留在上方。
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
  YewneApiError,
  type ChatDemoRequest,
  type ChatDemoResponse,
  type HealthResponse,
  type HistoryMessage,
  type Persona,
} from "@/lib/api/yewne";
import {
  enqueueAudio,
  hadRealAudio,
  speakWithBrowser,
  stopAudioQueue,
  unlockAudio,
  whenQueueDone,
} from "@/lib/speech/playYewneSpeech";

import {
  clearSession,
  formatRelativeTime,
  getOrCreateExternalUserId,
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
  youyou: "来了？直接说吧，我在听。",
  nini: "我在。你可以直接说，不用想怎么开口。",
};

const PERSONA_LABELS: Record<Persona, string> = {
  youyou: "优优",
  nini: "妮妮",
};

type ConvTurn = PersistedConvTurn;

export default function DemoPage() {
  // null = 第一句话还没发过 / 用户尚未"开口定调"。
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [persona, setPersona] = useState<Persona>("nini");
  const [input, setInput] = useState("");
  const [reply, setReply] = useState<string>(PERSONA_GREETINGS.nini);
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
  const externalUserIdRef = useRef("");
  const historyEndRef = useRef<HTMLDivElement | null>(null);

  // 逐字渐显：语音每开一句把文字追加到 target，定时器让显示文字平滑追上 target。
  const revealTargetRef = useRef("");
  const revealShownRef = useRef(0);
  const revealTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopReveal() {
    if (revealTimerRef.current) {
      clearInterval(revealTimerRef.current);
      revealTimerRef.current = null;
    }
  }

  function resetReveal() {
    stopReveal();
    revealTargetRef.current = "";
    revealShownRef.current = 0;
  }

  function ensureReveal() {
    if (revealTimerRef.current) return;
    revealTimerRef.current = setInterval(() => {
      const target = revealTargetRef.current;
      if (revealShownRef.current >= target.length) {
        stopReveal();
        return;
      }
      revealShownRef.current = Math.min(target.length, revealShownRef.current + 1);
      setReply(target.slice(0, revealShownRef.current));
    }, 85);
  }

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
    clearSession(persona);
    setHistory([]);
    setConversationId(null);
    setTurns([]);
    setReply(PERSONA_GREETINGS[persona]);
    setReplyKey((k) => k + 1);
    setRestoredAt(null);
    setError(null);
    setEmotion("");
  }

  function handlePersonaChange(next: Persona) {
    if (next === persona) return;

    // 先保存当前人格的会话，切回来时能恢复。
    saveSession(persona, {
      history,
      conversationId,
      turns,
    });

    // 停掉当前播放/请求/渐显。
    stopAudioQueue();
    resetReveal();
    setSpeaking(false);
    abortRef.current?.abort();
    setLoading(false);
    setError(null);
    setEmotion("");

    // 切换并加载目标人格自己的历史。
    setPersona(next);
    const saved = loadSession(next);
    if (saved) {
      setHistory(saved.history);
      setConversationId(saved.conversationId);
      setTurns(saved.turns);
      setRestoredAt(saved.savedAt);
      setReply(
        saved.turns.length > 0
          ? saved.turns[saved.turns.length - 1].reply
          : PERSONA_GREETINGS[next],
      );
    } else {
      setHistory([]);
      setConversationId(null);
      setTurns([]);
      setRestoredAt(null);
      setReply(PERSONA_GREETINGS[next]);
    }
    setReplyKey((k) => k + 1);
  }

  useEffect(() => {
    // mount 时加载当前（初始）人格的会话。
    externalUserIdRef.current = getOrCreateExternalUserId();
    const saved = loadSession(persona);
    if (saved) {
      /* eslint-disable react-hooks/set-state-in-effect -- mount 时恢复浏览器本地会话 */
      setHistory(saved.history);
      setConversationId(saved.conversationId);
      setTurns(saved.turns);
      setRestoredAt(saved.savedAt);
      if (saved.turns.length > 0) {
        setReply(saved.turns[saved.turns.length - 1].reply);
      }
      /* eslint-enable react-hooks/set-state-in-effect */
    }
    const ctrl = new AbortController();
    fetchHealth({ signal: ctrl.signal }).then(setHealth).catch(() => {});
    return () => {
      ctrl.abort();
      stopAudioQueue();
      stopReveal();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function applyReply(text: string) {
    setReply(text);
    setReplyKey((k) => k + 1);
  }

  async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim();

    // Always interrupt active speech/stream before anything else.
    abortRef.current?.abort();
    stopAudioQueue();
    resetReveal();
    setSpeaking(false);

    if (!text) {
      setLoading(false);
      return;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    setInput("");
    setEmotion("");
    const activeExternalUserId =
      externalUserIdRef.current || getOrCreateExternalUserId();
    externalUserIdRef.current = activeExternalUserId;
    const payload: ChatDemoRequest = {
      user_text: text,
      external_user_id: activeExternalUserId,
      conversation_id: conversationId,
      persona,
      history,
    };
    setLastCurl(buildCurl(payload, API_BASE));

    // Capture state values for use inside callbacks (React closure safety).
    const capturedHistory = history;
    const capturedTurns = turns;
    const capturedConversationId = conversationId;

    // 逐句显示：每句语音开播时把对应文字追加上去，文字与语音同步出现。
    let streamedText = "";
    let streamStarted = false;

    try {
      await fetchChatDemoStream(
        payload,
        {
          onAudio: (ev) => {
            enqueueAudio(ev.audio_base64, ev.content_type, ev.is_mock, () => {
              // 旧后端不带 text 时跳过，回退到 onDone 一次性显示的旧行为。
              if (ctrl.signal.aborted || !ev.text) return;
              if (!streamStarted) {
                streamStarted = true;
                setLoading(false);
                setSpeaking(true);
                setReplyKey((k) => k + 1); // 只在第一句淡入一次
              }
              // 把这句文字加进目标，逐字渐显的定时器会平滑追上来。
              streamedText += ev.text;
              revealTargetRef.current = streamedText;
              ensureReveal();
            });
          },
          onDone: (ev) => {
            if (ctrl.signal.aborted) return;

            // 已逐句显示则把目标补全为完整回复（逐字渐显继续走完）；
            // 否则（mock/无音频）按旧行为淡入全文。
            if (streamStarted) {
              revealTargetRef.current = ev.reply;
              ensureReveal();
            } else {
              applyReply(ev.reply);
            }
            const nextConversationId =
              ev.conversation_id ?? capturedConversationId;
            if (nextConversationId !== capturedConversationId) {
              setConversationId(nextConversationId);
            }
            if (ev.emotion) setEmotion(ev.emotion);

            const nextHistory: HistoryMessage[] = [
              ...capturedHistory,
              { role: "user" as const, content: text },
              { role: "assistant" as const, content: ev.reply },
            ];
            setHistory(nextHistory);

            const nextTurns = [...capturedTurns, { userText: text, reply: ev.reply }];
            setTurns(nextTurns);
            saveSession(persona, {
              history: nextHistory,
              conversationId: nextConversationId,
              turns: nextTurns,
            });
            setRestoredAt(null);

            setLastResponse({
              reply: ev.reply,
              safety_flag: ev.safety_flag,
              is_mock: ev.is_mock,
              request_id: ev.request_id,
              conversation_id: nextConversationId,
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
        err instanceof YewneApiError
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

  // 全部历史轮次（不含当前回复，当前回复在下方作为主焦点展示）
  const recentTurns = turns.slice(0, -1);

  return (
    <div className="relative flex min-h-dvh flex-1 flex-col bg-[#faf6f0] text-stone-900 dark:bg-[#1a1612] dark:text-stone-100">
      <style>{`
        @keyframes yewne-fade-in {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes yewne-fade-up {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 0.55; transform: translateY(0); }
        }
        @keyframes yewne-tentacle-think {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
        .yewne-history-turn {
          animation: yewne-fade-up 380ms ease-out both;
        }
      `}</style>

      <header className="flex items-start justify-between px-6 pt-6 sm:px-10 sm:pt-10">
        <div>
          <h1 className="text-lg font-medium tracking-tight">{PERSONA_LABELS[persona]}</h1>
          <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
            {persona === "youyou" ? "有什么就说。" : "先把问题变小。"}
          </p>
        </div>
        <div className="flex gap-1 rounded-xl bg-stone-100 p-1 dark:bg-stone-800">
          {(["youyou", "nini"] as Persona[]).map((p) => (
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
            style={{ animation: "yewne-fade-in 380ms ease-out both" }}
          >
            <span className="text-xs text-stone-400 dark:text-stone-500">感受到了</span>
            <span className="text-sm font-medium text-stone-600 dark:text-stone-300">{emotion}</span>
          </div>
        )}

        {/* 历史气泡区：最近几轮对话，小字 + 半透明 */}
        {recentTurns.length > 0 && (
          <div className="flex w-full max-w-md flex-col gap-3">
            {recentTurns.map((turn, i) => (
              <div key={i} className="yewne-history-turn flex flex-col gap-1 opacity-55">
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
            style={{ animation: "yewne-fade-in 420ms ease-out both" }}
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

        {/* 输入框 */}
        <div className="w-full max-w-md">
          <div className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-white/70 p-2 focus-within:border-[#e88c6a] focus-within:bg-white dark:border-stone-800 dark:bg-stone-900/60 dark:focus-within:border-[#c66645] dark:focus-within:bg-stone-900">
            <VoiceInputButton
              disabled={loading}
              speaking={speaking}
              startTrigger={recordingTrigger}
              conversationActive={conversationActive}
              onStartConversation={handleStartConversation}
              onEndConversation={handleEndConversation}
              onInterruptSpeaking={() => {
                stopAudioQueue();
                setSpeaking(false);
                setLoading(false);
                abortRef.current?.abort();
                setRecordingTrigger((t) => t + 1);
              }}
              onPhaseChange={setVoicePhase}
              onTranscript={(text) => void handleSend(text)}
              onError={setError}
            />
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="说点什么，或点左边麦克风…"
              maxLength={2000}
              rows={1}
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-base leading-relaxed text-stone-900 placeholder-stone-400 outline-none disabled:opacity-60 dark:text-stone-100 dark:placeholder-stone-500"
            />
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
