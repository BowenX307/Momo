"use client";

/**
 * /yewne/chat —— 高级版 demo 的对话页。
 *
 * 左右布局:左 40% 小人(idle/思考/写中 三态),右 60% 最新回复(手写体大字、逐字浮现)+ 输入。
 * 不是聊天气泡流,是"焦点句"。流式/逐字渐显/语音/打断/人格/会话逻辑都在本文件里。
 *
 * TODO(素材):CHAR_IMG 的 thinking / writing 现在用占位图,待换成"思考"和"趴着写字"两张。
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";

import {
  fetchAftercare,
  fetchCloseConversation,
  fetchChatDemoStream,
  fetchImportCurrentConversation,
  fetchMe,
  fetchLogout,
  fetchRoundMessages,
  fetchRounds,
  YewneApiError,
  type ChatDemoRequest,
  type HistoryMessage,
  type Persona,
  type RoundMessage,
  type RoundSummary,
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
  getOrCreateClientSessionId,
  getOrCreateExternalUserId,
  loadSession,
  saveSession,
  setExternalUserId,
  type ConvTurn,
} from "@/lib/session/persistSession";
import {
  clearAuthToken,
  getAuthToken,
  getStoredPhoneNumber,
  maskPhoneNumber,
  setAuthToken,
} from "@/lib/session/authToken";
import {
  VoiceInputButton,
  type VoicePhase,
} from "@/app/_shared/VoiceInputButton";
import { LoginPanel } from "@/app/yewne/chat/_components/LoginPanel";
import { PasswordPanel } from "@/app/yewne/chat/_components/PasswordPanel";

const PERSONA_GREETINGS: Record<Persona, string> = {
  youyou: "来了？直接说吧，我听着。",
  nini: "我在。不用想怎么开口，先说一句。",
};

const PERSONAS: Persona[] = ["youyou", "nini"];

/**
 * 输入栏那四个按钮的说明，供顶栏「按钮说明」展开使用。
 *
 * 图标与实际按钮上用的是同一份 path，改按钮图标时这里要一起改，否则说明和界面对不上。
 * 「结束这一轮」特意写明会存下来：那个按钮除了出拍立得还会把整轮对话归档，
 * 而界面上原本没有任何提示。
 */
const BUTTON_GUIDE: { label: string; desc: string; icon: React.ReactNode }[] = [
  {
    label: "说话",
    desc: "按住说，松开自动转成文字发出去",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0" />
        <line x1="12" y1="18" x2="12" y2="21.5" />
      </svg>
    ),
  },
  {
    label: "聊过的话",
    desc: "翻看这一轮里已经说过的内容",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z" />
      </svg>
    ),
  },
  {
    label: "往期",
    desc: "看以前结束过的那些轮次",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <circle cx="12" cy="13" r="8" />
        <path d="M12 9v4l2.5 1.5" />
        <path d="M9 2.5h6" />
      </svg>
    ),
  },
  {
    label: "结束这一轮",
    desc: "出一张拍立得，这轮对话会存下来，之后能在「往期」里看到",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M8.5 12.3l2.3 2.3 4.7-4.7" />
      </svg>
    ),
  },
];

// 小人三态对应的图。thinking / writing 待换成真实姿势(思考 / 趴着写字)。
type CharState = "idle" | "thinking" | "writing";
const CHAR_IMG: Record<CharState, string> = {
  idle: "/yewne/yewne-write.png",
  thinking: "/yewne/yewne-write.png", // TODO 换成"思考"横构图
  writing: "/yewne/yewne-write.png",
};

// 圆角羽化遮罩,让小人融进纸背景(同 hero 手法)。
const CHAR_MASK =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 133 100' preserveAspectRatio='none'%3E%3Cfilter id='f' x='-40%25' y='-40%25' width='180%25' height='180%25'%3E%3CfeGaussianBlur stdDeviation='8'/%3E%3C/filter%3E%3Crect x='18' y='13' width='97' height='74' rx='16' fill='%23fff' filter='url(%23f)'/%3E%3C/svg%3E\")";

const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.5' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.7'/%3E%3C/svg%3E\")";

// 更细的纸纹,给输入框用
const GRAIN_FINE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.7'/%3E%3C/svg%3E\")";

// ── 拍立得 Aftercare ──────────────────────────────────────────────
// 点"结束"结束这一轮 → 一张宽幅拍立得摇出,同时这轮对话归档。正面 POV 自拍(按情绪变),
// 背面手写(金句 + 于你这边同时发生的事 + 署名 + 时间戳)。demo 阶段 hardcode,
// 情绪档可手动左右切换。TODO(素材):front 图先用现有形象占位,待换成情绪自拍图。
type Mood = {
  key: string;
  label: string;
  img: string; // TODO 换成情绪专属 POV 自拍(扮鬼脸/比心/安静朝你笑…)
  caption: string; // 正面白边下的手写小字
  quote: string; // 背面金句(\n 换行)
};
const MOODS: Mood[] = [
  {
    key: "down",
    label: "有点低落",
    img: "/yewne/polaroid-down.png",
    caption: "今天有点重，对吧。",
    quote: "不是所有问题都要今晚解决，\n今晚的任务，只是好好活到明天。",
  },
  {
    key: "anxious",
    label: "有点焦虑",
    img: "/yewne/polaroid-anxious.png",
    caption: "脑子转太快了，先停一下。",
    quote: "今日份 CPU 过热，\n先关机散热十分钟。",
  },
  {
    key: "calm",
    label: "很平静",
    img: "/yewne/polaroid-calm.png",
    caption: "这样，就很好。",
    quote: "你今天已经做得够多了，\n剩下的，交给明天。",
  },
];

// 拍立得背面署名。"我这边发生的事"已由回信正文承载(小天地意象内嵌在 prompt 里)。
const PERSONA_SIGN: Record<Persona, string> = {
  youyou: "优优",
  nini: "妮妮",
};

function makeStamp() {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const h = d.getHours();
  const flavor =
    h < 5 ? "凌晨" : h < 11 ? "清晨" : h < 14 ? "午后" : h < 18 ? "傍晚" : h < 23 ? "夜里" : "深夜";
  return { date: `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())}`, flavor };
}

export default function YewneChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [persona, setPersona] = useState<Persona>("nini");
  const [input, setInput] = useState("");
  const [reply, setReply] = useState<string>(PERSONA_GREETINGS.nini);
  const [replyKey, setReplyKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showButtonGuide, setShowButtonGuide] = useState(false);
  const [pendingUser, setPendingUser] = useState("");
  // 拍立得 aftercare
  const [showPolaroid, setShowPolaroid] = useState(false);
  const [moodIndex, setMoodIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [polaroidLoading, setPolaroidLoading] = useState(false);
  // 后端现写的回信(据真实对话判 12 场景);为 null 时回落到该情绪档 curated 金句
  const [dynamicLetter, setDynamicLetter] = useState<string | null>(null);
  const [stamp, setStamp] = useState<{ date: string; flavor: string }>({ date: "", flavor: "" });
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [turns, setTurns] = useState<ConvTurn[]>([]);
  const [recordingTrigger, setRecordingTrigger] = useState(0);
  const [conversationActive, setConversationActive] = useState(false);
  const conversationActiveRef = useRef(false);
  // 往期:历史轮次列表 + 选中的某一轮
  const [showRounds, setShowRounds] = useState(false);
  const [rounds, setRounds] = useState<RoundSummary[]>([]);
  const [roundsLoading, setRoundsLoading] = useState(false);
  const [roundsError, setRoundsError] = useState<string | null>(null);
  const [selectedRound, setSelectedRound] = useState<RoundSummary | null>(null);
  const [selectedMessages, setSelectedMessages] = useState<RoundMessage[] | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);
  // 登录(手机号 + 验证码 / 密码两条路径)
  const [showLogin, setShowLogin] = useState(false);
  const [loggedInPhone, setLoggedInPhone] = useState<string | null>(null);
  // 这个账号有没有设过密码,决定「设置密码」还是「修改密码」
  const [hasPassword, setHasPassword] = useState(false);
  const [showPasswordPanel, setShowPasswordPanel] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const externalUserIdRef = useRef("");
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
    saveSession(persona, {
      history,
      conversationId,
      turns,
    });
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
      setConversationId(saved.conversationId);
      setTurns(saved.turns);
      setReply(
        saved.turns.length > 0
          ? saved.turns[saved.turns.length - 1].reply
          : PERSONA_GREETINGS[next],
      );
    } else {
      setHistory([]);
      setConversationId(null);
      setTurns([]);
      setReply(PERSONA_GREETINGS[next]);
    }
    setReplyKey((k) => k + 1);
  }

  useEffect(() => {
    externalUserIdRef.current = getOrCreateExternalUserId();
    const saved = loadSession(persona);
    if (saved && saved.turns.length > 0) {
      /* eslint-disable react-hooks/set-state-in-effect -- mount 时恢复浏览器本地会话 */
      setHistory(saved.history);
      setConversationId(saved.conversationId);
      setTurns(saved.turns);
      setReply(saved.turns[saved.turns.length - 1].reply);
      /* eslint-enable react-hooks/set-state-in-effect */
    }

    // 恢复登录态:本地存的 token 还有效就显示已登录;失效了静默清掉,回落匿名模式。
    const token = getAuthToken();
    if (token) {
      void fetchMe(token).then((me) => {
        if (me) {
          setLoggedInPhone(me.phone_number ?? getStoredPhoneNumber());
          setHasPassword(me.has_password ?? false);
          setExternalUserId(me.external_user_id);
          externalUserIdRef.current = me.external_user_id;
        } else {
          clearAuthToken();
        }
      });
    }

    return () => {
      abortRef.current?.abort();
      stopAudioQueue();
      stopReveal();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!conversationId || !getAuthToken()) return;
    const closeOnPageHide = () => {
      void fetchCloseConversation(conversationId, "browser_close", {
        keepalive: true,
      });
    };
    window.addEventListener("pagehide", closeOnPageHide);
    return () => window.removeEventListener("pagehide", closeOnPageHide);
  }, [conversationId]);

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

  // 结束这一轮:据真实对话现拍一张拍立得(后端判 12 场景→情绪档选照片+按人格写回信),
  // 同时把这轮标记为已结束归档(ended_at/mood/letter 落库,计入 7 轮上限,可在"往期"里回看)。
  // 失败静默落 calm,保证永远出片;归档失败也不影响拍立得展示和本地重置。
  async function handleEndRound() {
    if (polaroidLoading || turns.length === 0) return;
    setPolaroidLoading(true);
    const stampNow = makeStamp();
    const activeExternalUserId =
      externalUserIdRef.current || getOrCreateExternalUserId();
    try {
      const res = await fetchAftercare({
        persona,
        history,
        conversation_id: conversationId,
        external_user_id: activeExternalUserId,
      });
      const idx = MOODS.findIndex((m) => m.key === res.mood);
      setMoodIndex(idx >= 0 ? idx : 2); // 找不到落 calm
      setDynamicLetter(res.letter || res.quote); // 旧后端没有 letter 字段时退回 quote
    } catch {
      setMoodIndex(2); // calm 兜底
      setDynamicLetter(null);
    } finally {
      setStamp(stampNow);
      setFlipped(false);
      setPolaroidLoading(false);
      setShowPolaroid(true);
      // 这轮已经归档,清空本地状态回到打招呼,下一句话会开新的一轮。
      clearSession(persona);
      setHistory([]);
      setTurns([]);
      setConversationId(null);
      setPendingUser("");
      setReply(PERSONA_GREETINGS[persona]);
      setReplyKey((k) => k + 1);
    }
  }

  // 登录成功后存 token，并把当前游客会话自动导入后端认定的账号。
  async function handleLoginSuccess(result: {
    token: string;
    externalUserId: string;
    phoneNumber: string;
    expiresInSeconds: number;
  }) {
    setAuthToken(result.token, result.phoneNumber);
    setLoggedInPhone(result.phoneNumber);
    setShowLogin(false);
    // 验证码登录时前端并不知道这个账号有没有密码,问一下后端。
    void fetchMe(result.token).then((me) => setHasPassword(me?.has_password ?? false));

    setExternalUserId(result.externalUserId);
    externalUserIdRef.current = result.externalUserId;

    if (turns.length > 0) {
      const messages: HistoryMessage[] = turns.flatMap((turn) => [
        { role: "user" as const, content: turn.userText },
        { role: "assistant" as const, content: turn.reply },
      ]);
      try {
        const imported = await fetchImportCurrentConversation({
          client_session_id: getOrCreateClientSessionId(persona),
          persona,
          messages,
        });
        setConversationId(imported.conversation_id);
        saveSession(persona, {
          history,
          conversationId: imported.conversation_id,
          turns,
        });
      } catch {
        // 登录不因游客会话导入失败而失效；当前内容仍保留在浏览器。
      }
    }
  }

  // 退出登录:只结束这次登录态(token 失效),不清匿名身份/聊天记录——
  // 这个账号的数据还在,只是暂时不带 token 请求了。
  function handleLogout() {
    const token = getAuthToken();
    if (token) void fetchLogout(token);
    clearAuthToken();
    setLoggedInPhone(null);
    setHasPassword(false);
  }

  // 往期:拉这个匿名用户已结束归档的轮次列表(最新在前)。
  async function handleOpenRounds() {
    setShowHistory(false);
    setShowRounds(true);
    setSelectedRound(null);
    setSelectedMessages(null);
    setRoundsLoading(true);
    setRoundsError(null);
    try {
      const uid = externalUserIdRef.current || getOrCreateExternalUserId();
      setRounds(await fetchRounds(uid));
    } catch {
      setRoundsError("往期加载失败，晚点再试试。");
    } finally {
      setRoundsLoading(false);
    }
  }

  // 点某一轮:拉这一轮的完整消息(只读回看)。
  async function handleOpenRound(round: RoundSummary) {
    setSelectedRound(round);
    setSelectedMessages(null);
    setSelectedLoading(true);
    try {
      const uid = externalUserIdRef.current || getOrCreateExternalUserId();
      setSelectedMessages(await fetchRoundMessages(round.conversation_id, uid));
    } catch {
      setSelectedMessages([]);
    } finally {
      setSelectedLoading(false);
    }
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

    const capturedHistory = history;
    const capturedTurns = turns;
    const capturedConversationId = conversationId;

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
            const nextConversationId =
              ev.conversation_id ?? capturedConversationId;
            if (nextConversationId !== capturedConversationId) {
              setConversationId(nextConversationId);
            }

            const nextHistory: HistoryMessage[] = [
              ...capturedHistory,
              { role: "user" as const, content: text },
              { role: "assistant" as const, content: ev.reply },
            ];
            setHistory(nextHistory);
            const nextTurns = [...capturedTurns, { userText: text, reply: ev.reply }];
            setTurns(nextTurns);
            setPendingUser("");
            saveSession(persona, {
              history: nextHistory,
              conversationId: nextConversationId,
              turns: nextTurns,
            });

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
        err instanceof YewneApiError
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
        .font-yewne  { font-family: 'Caveat', cursive; }
        .font-kid  { font-family: 'Patrick Hand', cursive; }
        @keyframes yewne-fade-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .yewne-fade-in { animation: yewne-fade-in 420ms ease-out both; }

        /* 拍立得:摇出入场 + 3D 翻面 + 快门闪光 */
        .pol-scene { perspective: 1400px; }
        @keyframes pol-in { 0% { opacity: 0; transform: translateY(-28px); } 100% { opacity: 1; transform: translateY(0); } }
        .pol-in { animation: pol-in 640ms cubic-bezier(0.16,1,0.3,1) both; }
        .pol-card { transform-style: preserve-3d; transition: transform 660ms cubic-bezier(0.2,0.75,0.2,1); transform: rotateZ(-2deg); }
        .pol-card.flipped { transform: rotateZ(-2deg) rotateY(180deg); }
        .pol-face { -webkit-backface-visibility: hidden; backface-visibility: hidden; }
        .pol-back { transform: rotateY(180deg); }
        @keyframes pol-flash { 0% { opacity: 0; } 10% { opacity: .85; } 100% { opacity: 0; } }
        .pol-flash { animation: pol-flash 520ms ease-out both; }
        @media (prefers-reduced-motion: reduce) {
          .pol-in { animation: none; }
          .pol-card { transition: none; }
          .pol-flash { animation: none; opacity: 0; }
        }
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
          href="/yewne"
          className="inline-flex items-center gap-1.5 font-hand text-lg text-[#504437]/55 transition-colors hover:text-[#504437]"
          style={{ filter: "url(#crayon-soft)" }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M14 6l-6 6 6 6" />
          </svg>
          回去
        </Link>
        <div className="flex items-center gap-5">
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
          {/* 输入栏那四个按钮全是纯图标,没有文字也没有 title,新用户看不出各自干什么。
              放在这里而不是人格切换左边:和「登录/注册」同为 text-sm 的小字,挨在一起
              比被夹在「回去」和 text-2xl 的人格名之间整齐。 */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowButtonGuide((v) => !v)}
              aria-expanded={showButtonGuide}
              className="font-hand text-sm text-[#504437]/45 transition-colors hover:text-[#d66e76]"
              style={{ filter: "url(#crayon-soft)" }}
            >
              按钮说明
            </button>
            {showButtonGuide && (
              <div className="absolute right-0 top-8 z-30 w-64 rounded-2xl border border-[#e3d8c2] bg-[#faf6ec] p-4 shadow-lg">
                <ul className="flex flex-col gap-3">
                  {BUTTON_GUIDE.map((item) => (
                    <li key={item.label} className="flex items-start gap-2.5">
                      <span className="mt-0.5 shrink-0 text-[#504437]/70">
                        {item.icon}
                      </span>
                      <span className="font-hand text-sm leading-snug text-[#504437]/75">
                        <span className="text-[#504437]">{item.label}</span>
                        <br />
                        {item.desc}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          {loggedInPhone ? (
            <div
              className="flex items-center gap-2 font-hand text-sm text-[#504437]/45"
              style={{ filter: "url(#crayon-soft)" }}
            >
              <span>{maskPhoneNumber(loggedInPhone)}</span>
              <span aria-hidden>·</span>
              <button
                type="button"
                onClick={() => setShowPasswordPanel(true)}
                aria-label={hasPassword ? "修改密码" : "设置密码"}
                className="transition-colors hover:text-[#d66e76]"
              >
                {hasPassword ? "修改密码" : "设置密码"}
              </button>
              <span aria-hidden>·</span>
              <button
                type="button"
                onClick={handleLogout}
                aria-label="退出登录"
                className="transition-colors hover:text-[#d66e76]"
              >
                退出
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowLogin(true)}
              aria-label="登录/注册"
              className="font-hand text-sm text-[#504437]/45 transition-colors hover:text-[#d66e76]"
              style={{ filter: "url(#crayon-soft)" }}
            >
              登录/注册
            </button>
          )}
        </div>
      </div>

      {showLogin && (
        <LoginPanel
          externalUserId={getOrCreateExternalUserId()}
          onClose={() => setShowLogin(false)}
          onSuccess={handleLoginSuccess}
        />
      )}

      {showPasswordPanel && getAuthToken() && (
        <PasswordPanel
          token={getAuthToken() as string}
          hasPassword={hasPassword}
          onClose={() => setShowPasswordPanel(false)}
          onSuccess={() => {
            setHasPassword(true);
            setShowPasswordPanel(false);
          }}
        />
      )}

      {/* 主体:左小人 / 右回复+输入 */}
      <main className="relative z-10 flex min-h-dvh flex-col md:flex-row">
        {/* 左:小人(三态) */}
        <section className="flex items-center justify-center px-6 pt-24 md:w-[45%] md:pt-0">
          <div className="relative w-[380px] max-w-[82vw] sm:w-[460px]">
            <div style={{ WebkitMaskImage: CHAR_MASK, maskImage: CHAR_MASK, WebkitMaskSize: "100% 100%", maskSize: "100% 100%", WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat" }}>
              <Image
                src={CHAR_IMG[charState]}
                alt="于你"
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
            className="yewne-fade-in min-h-[3em] max-w-xl font-hand text-2xl leading-relaxed text-[#504437]/75 sm:text-3xl"
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
                sendClassName="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-[#d66e76] text-white transition-colors hover:bg-[#c2555e]"
                idleIcon={
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <rect x="9" y="3" width="6" height="11" rx="3" />
                    <path d="M5 11a7 7 0 0 0 14 0" />
                    <line x1="12" y1="18" x2="12" y2="21.5" />
                  </svg>
                }
              />
              {/* 录音时铅笔+结束按钮自动收起,只留麦克风(停止)+发送键,避免挤成四个 */}
              {voicePhase !== "recording" && (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      setShowRounds(false);
                      setShowHistory(true);
                    }}
                    aria-label="查看聊过的话"
                    className="flex h-9 w-9 shrink-0 items-center justify-center text-[#504437]/70 transition-colors hover:text-[#d66e76]"
                  >
                    <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      loggedInPhone
                        ? void handleOpenRounds()
                        : setShowLogin(true)
                    }
                    aria-label="往期"
                    className="flex h-9 w-9 shrink-0 items-center justify-center text-[#504437]/70 transition-colors hover:text-[#d66e76]"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <circle cx="12" cy="13" r="8" />
                      <path d="M12 9v4l2.5 1.5" />
                      <path d="M9 2.5h6" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={handleEndRound}
                    disabled={polaroidLoading || turns.length === 0}
                    aria-label="结束这一轮"
                    className="flex h-9 w-9 shrink-0 items-center justify-center text-[#504437]/70 transition-colors hover:text-[#d66e76] disabled:opacity-40"
                  >
                    {polaroidLoading ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="animate-spin" aria-hidden>
                        <path d="M21 12a9 9 0 1 1-6.2-8.5" />
                      </svg>
                    ) : (
                      <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                        <circle cx="12" cy="12" r="9" />
                        <path d="M8.5 12.3l2.3 2.3 4.7-4.7" />
                      </svg>
                    )}
                  </button>
                </>
              )}
              </div>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="写点什么…"
                maxLength={2000}
                rows={1}
                className="font-hand flex-1 resize-none bg-transparent px-2 py-1.5 text-lg leading-relaxed text-[#504437] outline-none placeholder:text-[#504437]/35"
              />
              {/* 主界面原先只有输入框没有发送键,只能靠 Enter——手机上没有物理 Enter,
                  等于打完字发不出去。样式与"聊过的话"那层的发送键保持一致。 */}
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
                    maxLength={2000}
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

      {/* 往期:已结束归档的历史轮次,列表 + 只读回看 */}
      {showRounds && (
        <div className="fixed inset-0 z-40">
          <div className="absolute inset-0 bg-[#f0e7d6]" />
          <div
            className="pointer-events-none absolute inset-0"
            style={{ backgroundImage: GRAIN, backgroundSize: "200px 200px", opacity: 0.5, mixBlendMode: "multiply" }}
          />

          <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-6 py-5 sm:px-10">
            {selectedRound ? (
              <button
                type="button"
                onClick={() => setSelectedRound(null)}
                className="inline-flex items-center gap-1.5 font-hand text-lg text-[#504437]/55 transition-colors hover:text-[#504437]"
                style={{ filter: "url(#crayon-soft)" }}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M14 6l-6 6 6 6" />
                </svg>
                往期
              </button>
            ) : (
              <span className="font-hand text-lg text-[#504437]/55">往期</span>
            )}
            <button
              type="button"
              onClick={() => setShowRounds(false)}
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

          <div className="absolute inset-0 overflow-y-auto px-6 pb-10 pt-20">
            <div className="mx-auto max-w-2xl">
              {!selectedRound ? (
                roundsLoading ? (
                  <p className="font-hand text-lg text-[#504437]/45">加载中…</p>
                ) : roundsError ? (
                  <p className="font-hand text-lg text-[#504437]/45">{roundsError}</p>
                ) : rounds.length === 0 ? (
                  <p className="font-hand text-lg text-[#504437]/45">还没有结束归档的轮次，聊完点&ldquo;结束&rdquo;就会存一轮。</p>
                ) : (
                  <div className="flex flex-col gap-3">
                    {rounds.map((r) => (
                      <button
                        key={r.conversation_id}
                        type="button"
                        onClick={() => void handleOpenRound(r)}
                        className="rounded-2xl border border-[#e3d8c2] bg-[#faf6ec] px-4 py-3 text-left transition-colors hover:border-[#d66e76]/50"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-hand text-base text-[#504437]">
                            {new Date(r.ended_at ?? r.created_at).toLocaleString()}
                          </span>
                          <span className="font-kid shrink-0 text-sm text-[#504437]/50">
                            {PERSONA_SIGN[r.persona]}
                          </span>
                        </div>
                        {r.letter && (
                          <p className="mt-1 truncate font-hand text-sm text-[#504437]/60">{r.letter}</p>
                        )}
                      </button>
                    ))}
                  </div>
                )
              ) : selectedLoading ? (
                <p className="font-hand text-lg text-[#504437]/45">加载中…</p>
              ) : (
                <div className="flex flex-col gap-7 pb-10">
                  {selectedRound.letter && (
                    <div className="rounded-2xl border border-[#e3d8c2] bg-[#faf6ec] px-5 py-4">
                      <p className="whitespace-pre-line font-hand text-base leading-relaxed text-[#504437]">
                        {selectedRound.letter}
                      </p>
                    </div>
                  )}
                  {(selectedMessages ?? []).map((m, i) =>
                    m.role === "user" ? (
                      <div key={i} className="flex justify-end">
                        <span className="max-w-[80%] rounded-2xl rounded-br-md bg-[#e7dcc6] px-4 py-2.5 font-hand text-[17px] leading-relaxed text-[#504437]">
                          {m.content}
                        </span>
                      </div>
                    ) : (
                      <div key={i} className="flex justify-start">
                        <span className="max-w-[85%] rounded-2xl rounded-bl-md bg-[#faf6ec] px-4 py-2.5 font-hand text-[17px] leading-relaxed text-[#504437] shadow-[0_6px_20px_rgba(120,100,70,0.08)]">
                          {m.content}
                        </span>
                      </div>
                    ),
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 拍立得 aftercare:点"结束"弹出,POV 自拍 + 翻面手写话,这轮已经归档 */}
      {showPolaroid && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-6">
          {/* 压暗背景,点击收起 */}
          <button
            type="button"
            aria-label="收起"
            onClick={() => setShowPolaroid(false)}
            className="absolute inset-0 cursor-default bg-[#3a2f26]/45 backdrop-blur-[2px]"
          />
          {/* 快门闪光:只在打开时闪一次,切情绪档不闪 */}
          <div className="pol-flash pointer-events-none absolute inset-0 z-20 bg-white" />

          <div className="relative z-10 flex w-[420px] max-w-[86vw] flex-col items-center">
            {/* 拍立得卡片 */}
            <div className="pol-in pol-scene w-full">
              <div
                className={`pol-card relative w-full cursor-pointer select-none ${flipped ? "flipped" : ""}`}
                style={{ aspectRatio: "420 / 330" }}
                onClick={() => setFlipped((f) => !f)}
              >
                {/* 正面:POV 自拍 */}
                <div className="pol-face absolute inset-0 flex flex-col rounded-[7px] bg-[#fbf7ee] p-3 pb-0 shadow-[0_22px_55px_rgba(60,45,30,0.4)]">
                  <div className="relative flex-1 overflow-hidden bg-[#ece2cd]">
                    <Image src={MOODS[moodIndex].img} alt="于你" fill sizes="420px" className="object-cover" />
                    <div
                      className="pointer-events-none absolute inset-0"
                      style={{ backgroundImage: GRAIN_FINE, backgroundSize: "140px 140px", opacity: 0.35, mixBlendMode: "multiply" }}
                    />
                  </div>
                  <div className="flex h-[62px] shrink-0 items-center justify-between px-1.5">
                    <span className="font-hand text-lg text-[#504437]/85" style={{ filter: "url(#crayon-soft)" }}>
                      {MOODS[moodIndex].caption}
                    </span>
                    <span className="font-yewne text-xl text-[#504437]/45">{stamp.date}</span>
                  </div>
                </div>

                {/* 背面:于你的回信(≤100 字,回落 curated 金句) */}
                <div className="pol-face pol-back absolute inset-0 flex flex-col rounded-[7px] bg-[#fbf7ee] p-6 shadow-[0_22px_55px_rgba(60,45,30,0.4)]">
                  <div
                    className="pointer-events-none absolute inset-0 rounded-[7px]"
                    style={{ backgroundImage: GRAIN_FINE, backgroundSize: "140px 140px", opacity: 0.4, mixBlendMode: "multiply" }}
                  />
                  <div className="relative z-10 flex h-full flex-col">
                    <p className="whitespace-pre-line font-hand text-[17px] leading-[1.9] text-[#504437]" style={{ filter: "url(#crayon-soft)" }}>
                      {dynamicLetter ?? MOODS[moodIndex].quote}
                    </p>
                    <svg className="mt-3 h-[8px] w-24" viewBox="0 0 120 8" preserveAspectRatio="none" fill="none" aria-hidden>
                      <path d="M2 5 Q 30 1 60 4 T 118 4" stroke="#d66e76" strokeOpacity="0.6" strokeWidth="2.4" strokeLinecap="round" />
                    </svg>
                    <div className="mt-auto flex items-end justify-between pt-3">
                      <span className="font-yewne text-3xl text-[#d66e76]" style={{ filter: "url(#crayon-soft)" }}>
                        {PERSONA_SIGN[persona]}
                      </span>
                      <span className="font-hand text-xs text-[#504437]/45">
                        {stamp.date} · {stamp.flavor}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 据这轮对话自动选匹配那张,不再手动翻页 */}
            <p className="pol-in mt-6 text-center font-hand text-sm text-[#f0e7d6]/55" style={{ animationDelay: "120ms" }}>
              点卡片翻面 · 点空白处收起
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
