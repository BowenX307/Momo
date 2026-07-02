"use client";

/**
 * /uni/chat —— 高级版 demo 的对话页。
 *
 * 左右布局:左 40% 小人(idle/思考/写中 三态),右 60% 最新回复(手写体大字、逐字浮现)+ 输入。
 * 不是聊天气泡流,是"焦点句"。功能逻辑复用 /demo(流式/逐字渐显/语音/打断/人格/会话)。
 *
 * TODO(素材):CHAR_IMG 的 thinking / writing 现在用占位图,待换成"思考"和"趴着写字"两张。
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";

import {
  API_BASE,
  fetchChatDemoStream,
  MomoApiError,
  type ChatDemoRequest,
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
  loadSession,
  saveSession,
  type ConvTurn,
} from "@/lib/session/persistSession";
import {
  VoiceInputButton,
  type VoicePhase,
} from "@/app/demo/_components/VoiceInputButton";

const PERSONA_GREETINGS: Record<Persona, string> = {
  momo: "我在的。慢慢说，我一直在。",
  iris: "来了？直接说吧，我听着。",
  rocky: "我在。不用想怎么开口，先说一句。",
};

// momo 下线,保留为"最初的人格"(仍在 Persona 类型/问候语/后端里),不再作为可选项。
const PERSONAS: Persona[] = ["iris", "rocky"];

// 小人三态对应的图。thinking / writing 待换成真实姿势(思考 / 趴着写字)。
type CharState = "idle" | "thinking" | "writing";
const CHAR_IMG: Record<CharState, string> = {
  idle: "/uni/uni-write.png",
  thinking: "/uni/uni-write.png", // TODO 换成"思考"横构图
  writing: "/uni/uni-write.png",
};

// 圆角羽化遮罩,让小人融进纸背景(同 hero 手法)。
const CHAR_MASK =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 133 100' preserveAspectRatio='none'%3E%3Cfilter id='f' x='-40%25' y='-40%25' width='180%25' height='180%25'%3E%3CfeGaussianBlur stdDeviation='8'/%3E%3C/filter%3E%3Crect x='18' y='13' width='97' height='74' rx='16' fill='%23fff' filter='url(%23f)'/%3E%3C/svg%3E\")";

const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.5' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.7'/%3E%3C/svg%3E\")";

// 更细的纸纹,给输入框用
const GRAIN_FINE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.7'/%3E%3C/svg%3E\")";

export default function UniChatPage() {
  const [scene, setScene] = useState<Scene | null>(null);
  const [persona, setPersona] = useState<Persona>("rocky");
  const [input, setInput] = useState("");
  const [reply, setReply] = useState<string>(PERSONA_GREETINGS.rocky);
  const [replyKey, setReplyKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [pendingUser, setPendingUser] = useState("");
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [turns, setTurns] = useState<ConvTurn[]>([]);
  const [recordingTrigger, setRecordingTrigger] = useState(0);
  const [conversationActive, setConversationActive] = useState(false);
  const conversationActiveRef = useRef(false);

  const abortRef = useRef<AbortController | null>(null);
  const historyScrollRef = useRef<HTMLDivElement | null>(null);

  // 逐字渐显
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
    unlockAudio();
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

  function handlePersonaChange(next: Persona) {
    if (next === persona) return;
    saveSession(persona, { history, scene, turns, savedAt: Date.now() });
    stopAudioQueue();
    resetReveal();
    setSpeaking(false);
    abortRef.current?.abort();
    setLoading(false);
    setError(null);
    setPersona(next);
    const saved = loadSession(next);
    if (saved) {
      setHistory(saved.history);
      setScene(saved.scene);
      setTurns(saved.turns);
      setReply(
        saved.turns.length > 0
          ? saved.turns[saved.turns.length - 1].reply
          : PERSONA_GREETINGS[next],
      );
    } else {
      setHistory([]);
      setScene(null);
      setTurns([]);
      setReply(PERSONA_GREETINGS[next]);
    }
    setReplyKey((k) => k + 1);
  }

  useEffect(() => {
    const saved = loadSession(persona);
    if (saved && saved.turns.length > 0) {
      setHistory(saved.history);
      setScene(saved.scene);
      setTurns(saved.turns);
      setReply(saved.turns[saved.turns.length - 1].reply);
    }
    return () => {
      abortRef.current?.abort();
      stopAudioQueue();
      stopReveal();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // focus 对话模式打开时,内容变化自动滚到底
  useEffect(() => {
    if (showHistory && historyScrollRef.current) {
      historyScrollRef.current.scrollTop = historyScrollRef.current.scrollHeight;
    }
  }, [showHistory, turns, reply, pendingUser, loading]);

  function applyReply(text: string) {
    setReply(text);
    setReplyKey((k) => k + 1);
  }

  async function handleSend(overrideText?: string) {
    const text = (overrideText ?? input).trim();

    unlockAudio(); // 点击/回车是用户手势,顺手解锁 iOS 音频
    abortRef.current?.abort();
    stopAudioQueue();
    resetReveal();
    setSpeaking(false);
    if (!text) {
      setLoading(false);
      setPendingUser("");
      return;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setLoading(true);
    setError(null);
    setInput("");
    setPendingUser(text);

    const payload: ChatDemoRequest = scene
      ? { user_text: text, scene, persona, history }
      : { user_text: text, persona, history };

    const capturedHistory = history;
    const capturedTurns = turns;
    const capturedScene = scene;

    let streamedText = "";
    let streamStarted = false;

    try {
      await fetchChatDemoStream(
        payload,
        {
          onAudio: (ev) => {
            enqueueAudio(ev.audio_base64, ev.content_type, ev.is_mock, () => {
              if (ctrl.signal.aborted || !ev.text) return;
              if (!streamStarted) {
                streamStarted = true;
                setLoading(false);
                setSpeaking(true);
                setReplyKey((k) => k + 1);
              }
              streamedText += ev.text;
              revealTargetRef.current = streamedText;
              ensureReveal();
            });
          },
          onDone: (ev) => {
            if (ctrl.signal.aborted) return;
            if (streamStarted) {
              revealTargetRef.current = ev.reply;
              ensureReveal();
            } else {
              applyReply(ev.reply);
            }
            if (ev.scene !== capturedScene) setScene(ev.scene);

            const nextHistory: HistoryMessage[] = [
              ...capturedHistory,
              { role: "user" as const, content: text },
              { role: "assistant" as const, content: ev.reply },
            ].slice(-20);
            setHistory(nextHistory);
            const nextTurns = [...capturedTurns, { userText: text, reply: ev.reply }];
            setTurns(nextTurns);
            setPendingUser("");
            saveSession(persona, { history: nextHistory, scene: ev.scene, turns: nextTurns, savedAt: Date.now() });

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
      if (!ctrl.signal.aborted) setLoading(false);
    } catch (err) {
      if (ctrl.signal.aborted) return;
      setError(
        err instanceof MomoApiError
          ? `连接后端失败（${err.status ?? "网络"}）`
          : err instanceof Error
            ? err.message
            : "未知错误",
      );
      setLoading(false);
      setPendingUser("");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void handleSend();
    }
  }

  const charState: CharState = loading ? "thinking" : speaking ? "writing" : "idle";
  const stateLabel = loading ? "在想…" : speaking ? "在写…" : "";

  const focalText =
    voicePhase === "recording"
      ? "我在听…"
      : voicePhase === "transcribing"
        ? "在听清…"
        : loading
          ? "在想…"
          : reply;

  return (
    <div className="relative min-h-dvh w-full overflow-hidden bg-[#f0e7d6] text-[#504437]">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&family=Caveat:wght@600;700&family=Patrick+Hand&display=swap');
        .font-hand { font-family: 'ZCOOL KuaiLe', cursive; }
        .font-uni  { font-family: 'Caveat', cursive; }
        .font-kid  { font-family: 'Patrick Hand', cursive; }
        @keyframes uni-fade-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .uni-fade-in { animation: uni-fade-in 420ms ease-out both; }
      `}</style>

      {/* 纸张颗粒 */}
      <div
        className="pointer-events-none absolute inset-0 z-0"
        style={{ backgroundImage: GRAIN, backgroundSize: "200px 200px", opacity: 0.5, mixBlendMode: "multiply" }}
      />

      {/* 蜡笔手绘滤镜(同 hero):把平滑文字边缘打毛 */}
      <svg className="absolute h-0 w-0" aria-hidden>
        <defs>
          <filter id="crayon">
            <feTurbulence type="fractalNoise" baseFrequency="0.06" numOctaves="3" seed="7" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="3.6" xChannelSelector="R" yChannelSelector="G" />
          </filter>
          <filter id="crayon-soft">
            <feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="2" seed="4" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="1.6" xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </defs>
      </svg>

      {/* 顶部:返回 + 人格切换 */}
      <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-6 py-5 sm:px-10">
        <Link
          href="/uni"
          className="inline-flex items-center gap-1.5 font-hand text-lg text-[#504437]/55 transition-colors hover:text-[#504437]"
          style={{ filter: "url(#crayon-soft)" }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M14 6l-6 6 6 6" />
          </svg>
          回去
        </Link>
        <div className="flex gap-4">
          {PERSONAS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => handlePersonaChange(p)}
              style={{ filter: "url(#crayon-soft)" }}
              className={`font-kid text-2xl transition-colors ${
                persona === p ? "text-[#d66e76]" : "text-[#504437]/40 hover:text-[#504437]/70"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* 主体:左小人 / 右回复+输入 */}
      <main className="relative z-10 flex min-h-dvh flex-col md:flex-row">
        {/* 左:小人(三态) */}
        <section className="flex items-center justify-center px-6 pt-24 md:w-[45%] md:pt-0">
          <div className="relative w-[380px] max-w-[82vw] sm:w-[460px]">
            <div style={{ WebkitMaskImage: CHAR_MASK, maskImage: CHAR_MASK, WebkitMaskSize: "100% 100%", maskSize: "100% 100%", WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat" }}>
              <Image
                src={CHAR_IMG[charState]}
                alt="uni"
                width={1448}
                height={1086}
                priority
                className="h-auto w-full select-none"
              />
            </div>
            <div className="mt-1 text-center font-hand text-base text-[#504437]/45">{stateLabel}</div>
          </div>
        </section>

        {/* 右:焦点句 + 输入 */}
        <section className="flex flex-1 flex-col justify-center gap-10 px-8 pb-10 md:pr-16 md:pl-4">
          <p
            key={replyKey}
            className="uni-fade-in min-h-[3em] max-w-xl font-hand text-2xl leading-relaxed text-[#504437]/75 sm:text-3xl"
            style={{ filter: "url(#crayon)" }}
          >
            {focalText}
          </p>

          <div className="w-full max-w-xl">
            <div className="relative rounded-2xl">
              {/* 纸卡:填充+边框同层一起打毛边(不裁剪→糙边不被切、也不脱开),纸纹靠圆角裁 */}
              <div
                className="pointer-events-none absolute inset-0 rounded-2xl border border-[#e3d8c2] bg-[#faf6ec]"
                style={{ filter: "url(#crayon-soft)" }}
              >
                <div
                  className="absolute inset-0 rounded-2xl"
                  style={{ backgroundImage: GRAIN_FINE, backgroundSize: "140px 140px", opacity: 0.5, mixBlendMode: "multiply" }}
                />
              </div>
              <div className="relative z-10 flex items-end gap-2 p-2" style={{ filter: "url(#crayon-soft)" }}>
              <div className="flex items-end">
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
                onTranscript={(t) => void handleSend(t)}
                onError={setError}
                showSilenceRing={false}
                className="text-[#504437]/70 hover:text-[#d66e76]"
                idleIcon={
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.3 0-2.5-.3-3.6-.8L3 21l1.8-5.9c-.5-1.1-.8-2.3-.8-3.6a8.5 8.5 0 0 1 17 0Z" />
                  </svg>
                }
              />
              <button
                type="button"
                onClick={() => setShowHistory(true)}
                aria-label="查看聊过的话"
                className="flex h-9 w-9 shrink-0 items-center justify-center text-[#504437]/70 transition-colors hover:text-[#d66e76]"
              >
                <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M12 20h9" />
                  <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z" />
                </svg>
              </button>
              </div>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="写点什么…"
                rows={1}
                className="font-hand flex-1 resize-none bg-transparent px-2 py-1.5 text-lg leading-relaxed text-[#504437] outline-none placeholder:text-[#504437]/35"
              />
              </div>
            </div>
            {error && <p className="mt-2 font-hand text-sm text-[#c2555e]">{error}</p>}
          </div>
        </section>
      </main>

      {/* focus 对话模式:铅笔点开,整屏气泡流 + 底部打字输入(仅打字),蜡笔风 */}
      {showHistory && (
        <div className="fixed inset-0 z-40">
          {/* 固定纸背景(不随滚动,无接缝) */}
          <div className="absolute inset-0 bg-[#f0e7d6]" />
          <div
            className="pointer-events-none absolute inset-0"
            style={{ backgroundImage: GRAIN, backgroundSize: "200px 200px", opacity: 0.5, mixBlendMode: "multiply" }}
          />

          {/* 顶栏:标题 + 关闭 */}
          <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-6 py-5 sm:px-10">
            <span className="font-hand text-lg text-[#504437]/55">聊过的话</span>
            <button
              type="button"
              onClick={() => setShowHistory(false)}
              aria-label="关闭"
              className="flex h-9 w-9 items-center justify-center text-[#504437]/60 transition-colors hover:text-[#504437]"
              style={{ filter: "url(#crayon-soft)" }}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            </button>
          </div>

          {/* 可滚动的气泡流 */}
          <div ref={historyScrollRef} className="absolute inset-0 overflow-y-auto px-6 pb-32 pt-20">
            <div className="mx-auto flex max-w-2xl flex-col gap-7">
              {turns.length === 0 && !pendingUser ? (
                <p className="font-hand text-lg text-[#504437]/45">还没聊过什么，写点什么吧。</p>
              ) : (
                <>
                  {turns.map((turn, i) => (
                    <div key={i} className="flex flex-col gap-2.5">
                      <div className="flex justify-end">
                        <span className="max-w-[80%] rounded-2xl rounded-br-md bg-[#e7dcc6] px-4 py-2.5 font-hand text-[17px] leading-relaxed text-[#504437]" style={{ filter: "url(#crayon-soft)" }}>
                          {turn.userText}
                        </span>
                      </div>
                      <div className="flex justify-start">
                        <span className="max-w-[85%] rounded-2xl rounded-bl-md bg-[#faf6ec] px-4 py-2.5 font-hand text-[17px] leading-relaxed text-[#504437] shadow-[0_6px_20px_rgba(120,100,70,0.08)]" style={{ filter: "url(#crayon-soft)" }}>
                          {turn.reply}
                        </span>
                      </div>
                    </div>
                  ))}
                  {pendingUser && (
                    <div className="flex flex-col gap-2.5">
                      <div className="flex justify-end">
                        <span className="max-w-[80%] rounded-2xl rounded-br-md bg-[#e7dcc6] px-4 py-2.5 font-hand text-[17px] leading-relaxed text-[#504437]" style={{ filter: "url(#crayon-soft)" }}>
                          {pendingUser}
                        </span>
                      </div>
                      <div className="flex justify-start">
                        <span className="max-w-[85%] rounded-2xl rounded-bl-md bg-[#faf6ec] px-4 py-2.5 font-hand text-[17px] leading-relaxed text-[#504437] shadow-[0_6px_20px_rgba(120,100,70,0.08)]" style={{ filter: "url(#crayon-soft)" }}>
                          {loading ? "在想…" : reply}
                        </span>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* 底部打字输入(仅打字,无语音) */}
          <div className="absolute inset-x-0 bottom-0 z-20 px-6 pb-6 sm:px-10">
            <div className="mx-auto max-w-2xl">
              <div className="relative rounded-2xl">
                <div
                  className="pointer-events-none absolute inset-0 rounded-2xl border border-[#e3d8c2] bg-[#faf6ec]"
                  style={{ filter: "url(#crayon-soft)" }}
                >
                  <div
                    className="absolute inset-0 rounded-2xl"
                    style={{ backgroundImage: GRAIN_FINE, backgroundSize: "140px 140px", opacity: 0.5, mixBlendMode: "multiply" }}
                  />
                </div>
                <div className="relative z-10 flex items-end gap-2 p-2" style={{ filter: "url(#crayon-soft)" }}>
                  <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="写点什么…"
                    rows={1}
                    className="font-hand flex-1 resize-none bg-transparent px-2 py-1.5 text-lg leading-relaxed text-[#504437] outline-none placeholder:text-[#504437]/35"
                  />
                  <button
                    type="button"
                    onClick={() => void handleSend()}
                    disabled={!input.trim() && !loading && !speaking}
                    aria-label={loading || speaking ? "打断" : "发送"}
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#d66e76] text-white transition-colors hover:bg-[#c2555e] disabled:cursor-not-allowed disabled:bg-[#d8ccb8]"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.3 0-2.5-.3-3.6-.8L3 21l1.8-5.9c-.5-1.1-.8-2.3-.8-3.6a8.5 8.5 0 0 1 17 0Z" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
