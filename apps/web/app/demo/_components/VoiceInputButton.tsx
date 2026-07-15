"use client";

/**
 * 点一下开始录音 → 说完自动停（VAD）→ 转写。
 *
 * VAD 策略：
 * 1. 前 400ms 校准环境噪音基线
 * 2. RMS 振幅：高于基线+18 → 在说；低于基线+6 → 静音
 * 3. 连续静音 1.2s 且已说过至少 0.6s → 自动停止
 * 4. 用户也可手动再点一次结束
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { fetchHealth, fetchTranscribe, MomoApiError } from "@/lib/api/momo";

export type VoicePhase = "idle" | "recording" | "transcribing";

function formatTranscribeError(err: unknown): string {
  if (err instanceof MomoApiError) {
    if (err.status === undefined) {
      const hint = err.message.toLowerCase();
      if (hint.includes("failed to fetch") || hint.includes("network")) {
        return "连不上转写服务，请确认后端已启动";
      }
      return `转写失败：${err.message}`;
    }
    if (err.status === 502) return "转写服务暂时出错，请再试一次";
    if (err.status === 413) return "录音太长了，请短一点";
    if (err.status === 415) return "不支持的音频格式";
    return `转写失败（${err.status}）`;
  }
  if (err instanceof Error) return err.message;
  return "转写失败";
}

interface Props {
  onTranscript: (text: string) => void;
  onError?: (message: string) => void;
  onPhaseChange?: (phase: VoicePhase) => void;
  disabled?: boolean;
  speaking?: boolean;
  startTrigger?: number;
  conversationActive?: boolean;
  onStartConversation?: () => void;
  onEndConversation?: () => void;
  onInterruptSpeaking?: () => void;
  /** 覆盖 idle 态图标(默认麦克风)。 */
  idleIcon?: ReactNode;
  /** 覆盖按钮样式(不传则用默认)。 */
  className?: string;
  /** 是否显示录音时的静音倒计时环(默认显示)。 */
  showSilenceRing?: boolean;
  /** 录音时"发送"按钮的样式(不传则用默认填充样式)。 */
  sendClassName?: string;
}

type SttMode = "browser" | "backend";

const MAX_RECORD_MS = 60_000;
const CALIBRATION_MS = 400;
const SILENCE_MS = 2200;
const MIN_SPEECH_MS = 1200;
const SPEECH_OFFSET = 5;
const SILENCE_OFFSET = 1.5;

interface SpeechRecognitionResultEvent {
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      [index: number]: { transcript: string };
    };
  };
}

interface BrowserSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  // iPadOS 13+ reports as MacIntel but has a touch screen.
  return (
    /iP(hone|ad|od)/.test(ua) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function getBrowserSpeechRecognition(): (new () => BrowserSpeechRecognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as Window & {
    SpeechRecognition?: new () => BrowserSpeechRecognition;
    webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t));
}

function measureRms(analyser: AnalyserNode, buf: Uint8Array<ArrayBuffer>): number {
  analyser.getByteTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) {
    const v = (buf[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / buf.length) * 100;
}

function collectTranscriptIncludingInterim(
  event: SpeechRecognitionResultEvent,
): string {
  let finals = "";
  for (let i = 0; i < event.results.length; i++) {
    if (event.results[i].isFinal) {
      finals += event.results[i][0]?.transcript ?? "";
    }
  }
  if (finals.trim()) return finals.trim();
  const last = event.results[event.results.length - 1];
  return (last?.[0]?.transcript ?? "").trim();
}

export function VoiceInputButton({
  onTranscript,
  onError,
  onPhaseChange,
  disabled,
  speaking,
  startTrigger,
  conversationActive,
  onStartConversation,
  onEndConversation,
  onInterruptSpeaking,
  idleIcon,
  className,
  showSilenceRing = true,
  sendClassName,
}: Props) {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [sttMode, setSttMode] = useState<SttMode>("backend");
  /** 0–1，静音倒计时进度（越满越接近自动停） */
  const [silenceProgress, setSilenceProgress] = useState(0);
  const [hasSpeech, setHasSpeech] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const vadRafRef = useRef<number | null>(null);
  const stoppingRef = useRef(false);

  // Barge-in: lightweight background VAD while AI is speaking
  const bargeInStreamRef = useRef<MediaStream | null>(null);
  const bargeInAudioCtxRef = useRef<AudioContext | null>(null);
  const bargeInRafRef = useRef<number | null>(null);
  const onInterruptSpeakingRef = useRef(onInterruptSpeaking);
  onInterruptSpeakingRef.current = onInterruptSpeaking;

  const speechRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechTranscriptRef = useRef("");

  const setPhaseAndNotify = useCallback(
    (next: VoicePhase) => {
      setPhase(next);
      onPhaseChange?.(next);
    },
    [onPhaseChange],
  );

  useEffect(() => {
    const browserCtor = getBrowserSpeechRecognition();
    fetchHealth()
      .then((health) => {
        if (health?.stt_is_mock === false) {
          setSttMode("backend");
        } else if (browserCtor) {
          setSttMode("browser");
        } else {
          setSttMode("backend");
        }
      })
      .catch(() => {
        setSttMode(browserCtor ? "browser" : "backend");
      });
  }, []);

  const stopBargeIn = useCallback(() => {
    if (bargeInRafRef.current !== null) {
      cancelAnimationFrame(bargeInRafRef.current);
      bargeInRafRef.current = null;
    }
    void bargeInAudioCtxRef.current?.close();
    bargeInAudioCtxRef.current = null;
    bargeInStreamRef.current?.getTracks().forEach((t) => t.stop());
    bargeInStreamRef.current = null;
  }, []);

  const startBargeIn = useCallback(async () => {
    if (bargeInStreamRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      bargeInStreamRef.current = stream;
      const audioCtx = new AudioContext();
      bargeInAudioCtxRef.current = audioCtx;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      audioCtx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize) as Uint8Array<ArrayBuffer>;

      const calStart = Date.now();
      const calSamples: number[] = [];
      let baseline = 8;
      // Same threshold as regular VAD; echo cancellation handles the AI's own audio.
      // Hysteresis: brief RMS dips (<150ms) don't reset the speech timer so natural
      // speech fluctuations don't prevent the 400ms window from completing.
      const BARGE_IN_OFFSET = SPEECH_OFFSET;
      const BARGE_IN_MS = 400;
      const BARGE_IN_SILENCE_RESET_MS = 150;
      let speechStart: number | null = null;
      let silenceStart: number | null = null;

      const tick = () => {
        if (!bargeInStreamRef.current) return;
        const raw = measureRms(analyser, buf);
        const now = Date.now();

        if (now - calStart < 300) {
          calSamples.push(raw);
          bargeInRafRef.current = requestAnimationFrame(tick);
          return;
        }
        if (calSamples.length > 0) {
          baseline = calSamples.reduce((a, b) => a + b, 0) / calSamples.length;
          calSamples.length = 0;
        }

        if (raw > baseline + BARGE_IN_OFFSET) {
          silenceStart = null;
          if (speechStart === null) speechStart = now;
          else if (now - speechStart >= BARGE_IN_MS) {
            stopBargeIn();
            onInterruptSpeakingRef.current?.();
            return;
          }
        } else {
          if (silenceStart === null) {
            silenceStart = now;
          } else if (now - silenceStart >= BARGE_IN_SILENCE_RESET_MS) {
            speechStart = null;
          }
        }

        bargeInRafRef.current = requestAnimationFrame(tick);
      };
      bargeInRafRef.current = requestAnimationFrame(tick);
    } catch {
      // mic unavailable, ignore
    }
  }, [stopBargeIn]);

  const cleanupStream = useCallback(() => {
    if (vadRafRef.current !== null) {
      cancelAnimationFrame(vadRafRef.current);
      vadRafRef.current = null;
    }
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setSilenceProgress(0);
    setHasSpeech(false);
  }, []);

  const cleanupSpeech = useCallback(() => {
    speechRef.current?.abort();
    speechRef.current = null;
    speechTranscriptRef.current = "";
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (maxTimerRef.current) clearTimeout(maxTimerRef.current);
      mediaRecorderRef.current?.stop();
      cleanupStream();
      cleanupSpeech();
      stopBargeIn();
    };
  }, [cleanupSpeech, cleanupStream, stopBargeIn]);

  // Barge-in: open background VAD whenever AI is speaking OR thinking (loading).
  // Echo cancellation filters the AI's own audio so it won't self-trigger.
  // NOT on iOS: opening the mic there switches the system to the VoIP audio
  // session, which ducks/cuts the AI's playback. iOS relies on tap-to-interrupt.
  useEffect(() => {
    if (conversationActive && (speaking || disabled) && phase === "idle" && !isIOS()) {
      void startBargeIn();
    } else {
      stopBargeIn();
    }
  }, [conversationActive, speaking, disabled, phase, startBargeIn, stopBargeIn]);

  const stopBackendRecording = useCallback(async () => {
    if (stoppingRef.current) return;
    stoppingRef.current = true;

    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      stoppingRef.current = false;
      return;
    }

    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop();
    });

    const mime = recorder.mimeType || pickMimeType() || "audio/webm";
    const blob = new Blob(chunksRef.current, { type: mime });
    chunksRef.current = [];
    mediaRecorderRef.current = null;
    cleanupStream();

    if (blob.size < 100) {
      setPhaseAndNotify("idle");
      onError?.("录音太短了，多说几个字。");
      stoppingRef.current = false;
      return;
    }

    setPhaseAndNotify("transcribing");
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetchTranscribe(blob, {
        signal: ctrl.signal,
        filename: mime.includes("mp4") ? "clip.m4a" : "clip.webm",
      });
      if (res.is_mock) {
        onError?.(
          "当前后端是 mock 转写。请配置 WHISPER_API_KEY，或用 Chrome 浏览器。",
        );
        return;
      }
      if (!res.text.trim()) {
        onError?.("没听清，再试一次？");
        return;
      }
      onTranscript(res.text);
    } catch (err) {
      if (ctrl.signal.aborted) return;
      onError?.(formatTranscribeError(err));
    } finally {
      if (!ctrl.signal.aborted) setPhaseAndNotify("idle");
      stoppingRef.current = false;
    }
  }, [cleanupStream, onError, onTranscript, setPhaseAndNotify]);

  const stopBackendRecordingRef = useRef(stopBackendRecording);
  stopBackendRecordingRef.current = stopBackendRecording;

  const startBackendRecording = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      onError?.("当前浏览器不支持麦克风。");
      return;
    }

    stoppingRef.current = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      const mime = pickMimeType();
      const recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.start(250);
      mediaRecorderRef.current = recorder;
      setPhaseAndNotify("recording");

      maxTimerRef.current = setTimeout(() => {
        void stopBackendRecordingRef.current();
      }, MAX_RECORD_MS);

      try {
        const audioCtx = new AudioContext();
        audioCtxRef.current = audioCtx;
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 512;
        audioCtx.createMediaStreamSource(stream).connect(analyser);
        const buf = new Uint8Array(analyser.fftSize) as Uint8Array<ArrayBuffer>;

        const calStart = Date.now();
        const calSamples: number[] = [];
        let baseline = 8;
        let speechStart: number | null = null;
        let silenceStart: number | null = null;
        // 5帧滑动平均，消除帧间抖动
        const rmsWindow: number[] = [];
        const WINDOW = 5;

        const tick = () => {
          const raw = measureRms(analyser, buf);
          const now = Date.now();

          // 校准阶段
          if (now - calStart < CALIBRATION_MS) {
            calSamples.push(raw);
            vadRafRef.current = requestAnimationFrame(tick);
            return;
          }
          if (calSamples.length > 0) {
            baseline = calSamples.reduce((a, b) => a + b, 0) / calSamples.length;
            calSamples.length = 0;
          }

          // 滑动平均平滑 RMS
          rmsWindow.push(raw);
          if (rmsWindow.length > WINDOW) rmsWindow.shift();
          const rms = rmsWindow.reduce((a, b) => a + b, 0) / rmsWindow.length;

          // 基线极慢漂移（只在静音期，速度很慢避免追着说话声跑）
          if (speechStart === null) {
            baseline = baseline * 0.998 + rms * 0.002;
          }

          const speechThreshold = baseline + SPEECH_OFFSET;
          const silenceThreshold = baseline + SILENCE_OFFSET;

          if (rms > speechThreshold) {
            // 检测到说话：重置静音计时
            if (speechStart === null) speechStart = now;
            silenceStart = null;
            setHasSpeech(true);
            setSilenceProgress(0);
          } else if (rms < silenceThreshold) {
            // 明确静音：开始或推进倒计时
            if (speechStart !== null && now - speechStart >= MIN_SPEECH_MS) {
              if (silenceStart === null) {
                silenceStart = now;
              } else {
                const elapsed = now - silenceStart;
                setSilenceProgress(Math.min(elapsed / SILENCE_MS, 1));
                if (elapsed >= SILENCE_MS) {
                  void stopBackendRecordingRef.current();
                  return;
                }
              }
            }
          }
          // 死区（两阈值之间）：什么都不做，让静音计时自然持续

          vadRafRef.current = requestAnimationFrame(tick);
        };
        vadRafRef.current = requestAnimationFrame(tick);
      } catch {
        // VAD 不可用时仍可手动停
      }
    } catch {
      cleanupStream();
      onError?.("需要麦克风权限才能说话。");
    }
  }, [cleanupStream, onError, setPhaseAndNotify]);

  const startBrowserSpeech = useCallback(() => {
    const Ctor = getBrowserSpeechRecognition();
    if (!Ctor) {
      onError?.("当前浏览器不支持语音识别，请用 Chrome。");
      return;
    }

    cleanupSpeech();
    speechTranscriptRef.current = "";

    const recognition = new Ctor();
    speechRef.current = recognition;
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
      const text = collectTranscriptIncludingInterim(event);
      if (text) speechTranscriptRef.current = text;
    };

    recognition.onerror = (event) => {
      if (event.error === "aborted") return;
      setPhaseAndNotify("idle");
      cleanupSpeech();
      if (event.error === "not-allowed") {
        onError?.("需要麦克风权限才能说话。");
      } else if (event.error === "no-speech") {
        onError?.("没听到声音，再试一次？");
      } else {
        onError?.("语音识别出了点问题，再试一次。");
      }
    };

    recognition.onend = () => {
      const text = speechTranscriptRef.current.trim();
      speechRef.current = null;
      setPhaseAndNotify("idle");
      if (text) {
        onTranscript(text);
      } else {
        onError?.("没听清，多说几个字。");
      }
    };

    try {
      recognition.start();
      setPhaseAndNotify("recording");
      maxTimerRef.current = setTimeout(() => {
        recognition.stop();
      }, MAX_RECORD_MS);
    } catch {
      cleanupSpeech();
      setPhaseAndNotify("idle");
      onError?.("无法启动语音识别，请用 Chrome 并重试。");
    }
  }, [cleanupSpeech, onError, onTranscript, setPhaseAndNotify]);

  // MOMO 说完后自动重听：trigger 递增时触发
  const prevTriggerRef = useRef(startTrigger ?? 0);
  useEffect(() => {
    const prev = prevTriggerRef.current;
    const cur = startTrigger ?? 0;
    prevTriggerRef.current = cur;
    if (cur <= prev || disabled || phase !== "idle") return;
    if (sttMode === "browser") {
      startBrowserSpeech();
    } else {
      void startBackendRecording();
    }
  }, [startTrigger, disabled, phase, sttMode, startBrowserSpeech, startBackendRecording]);

  const handleToggle = useCallback(() => {
    if (disabled || phase === "transcribing") return;

    // AI 说话时点麦克风 → 打断并立刻开始录音
    if (conversationActive && speaking && phase === "idle") {
      onInterruptSpeaking?.();
      return;
    }

    if (conversationActive) {
      // 对话模式中点击 → 结束对话（强制停止录音，不走转写）
      if (phase === "recording") {
        if (maxTimerRef.current) { clearTimeout(maxTimerRef.current); maxTimerRef.current = null; }
        stoppingRef.current = true;
        mediaRecorderRef.current?.stop();
        chunksRef.current = [];
        mediaRecorderRef.current = null;
        cleanupStream();
        if (sttMode === "browser") speechRef.current?.abort();
        setPhaseAndNotify("idle");
        stoppingRef.current = false;
      }
      onEndConversation?.();
    } else {
      // 未在对话模式 → 开始对话（parent 会触发 startTrigger）
      onStartConversation?.();
    }
  }, [
    conversationActive,
    speaking,
    disabled,
    phase,
    sttMode,
    cleanupStream,
    setPhaseAndNotify,
    onEndConversation,
    onStartConversation,
    onInterruptSpeaking,
  ]);

  // 手动"发送":录音时立刻结束并转写提交(不等 VAD 静音),嘈杂环境救急。
  const finishNow = useCallback(() => {
    if (phase !== "recording") return;
    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    if (sttMode === "browser") {
      speechRef.current?.stop(); // → onend → onTranscript
    } else {
      void stopBackendRecordingRef.current(); // 停录 → 转写 → onTranscript
    }
  }, [phase, sttMode]);

  const isRecording = phase === "recording";
  const isTranscribing = phase === "transcribing";
  const isBusy = disabled || isTranscribing;
  const isConversing = conversationActive ?? false;

  return (
    <div className="flex shrink-0 items-center gap-1.5">
    <div className="relative flex flex-col items-center">
      <button
        type="button"
        aria-pressed={isRecording}
        aria-label={
          isConversing
            ? "对话进行中，点击结束"
            : isTranscribing
              ? "正在转写…"
              : "点击开始对话"
        }
        disabled={isBusy}
        onClick={handleToggle}
        className={
          className
            ? "inline-flex h-9 w-9 items-center justify-center rounded-xl transition-colors disabled:cursor-not-allowed disabled:opacity-60 " +
              className
            : [
                "inline-flex h-9 w-9 items-center justify-center rounded-xl border transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-60",
                isConversing
                  ? "border-[#c0392b] bg-[#fdeee8] text-[#c0392b] ring-2 ring-[#f3d4c3]"
                  : "border-stone-200 bg-white text-stone-500 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400 dark:hover:bg-stone-800",
              ].join(" ")
        }
      >
        {isTranscribing ? (
          <span className="h-3 w-3 animate-pulse rounded-full bg-[#d97757]" />
        ) : isRecording ? (
          <span
            className={[
              "h-3 w-3 rounded-full bg-[#d97757]",
              hasSpeech ? "animate-pulse" : "",
            ].join(" ")}
          />
        ) : idleIcon ? (
          idleIcon
        ) : (
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" x2="12" y1="19" y2="22" />
          </svg>
        )}
      </button>
      {/* 静音倒计时环：说完后圆点逐渐填满 */}
      {showSilenceRing && isRecording && hasSpeech && silenceProgress > 0 && (
        <span
          className="absolute -bottom-1 h-1 w-7 overflow-hidden rounded-full bg-stone-200"
          aria-hidden="true"
        >
          <span
            className="block h-full rounded-full bg-[#d97757] transition-all duration-100"
            style={{ width: `${silenceProgress * 100}%` }}
          />
        </span>
      )}
    </div>

      {/* 录音时的"发送":立刻结束并提交,不用等静音 */}
      {isRecording && (
        <button
          type="button"
          onClick={finishNow}
          aria-label="发送"
          className={
            sendClassName ??
            "inline-flex h-9 w-9 items-center justify-center rounded-xl bg-[#d97757] text-white transition-opacity hover:opacity-90"
          }
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      )}
    </div>
  );
}
