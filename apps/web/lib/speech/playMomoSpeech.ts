/** 播放 MOMO 语音回复；mock 时降级到浏览器 speechSynthesis。 */

import type { SynthesizeResponse } from "@/lib/api/momo";

let currentAudio: HTMLAudioElement | null = null;
let currentAudioCtx: AudioContext | null = null;

export function stopMomoSpeech(): void {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  if (currentAudioCtx) {
    currentAudioCtx.close().catch(() => {});
    currentAudioCtx = null;
  }
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}

export function speakWithBrowser(text: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      reject(new Error("browser speech not supported"));
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.rate = 0.92;
    utterance.onend = () => resolve();
    utterance.onerror = () => reject(new Error("browser speech failed"));
    window.speechSynthesis.speak(utterance);
  });
}

const GAIN = 1.8;

function _playOneChunk(base64: string, contentType: string): Promise<void> {
  return new Promise((resolve) => {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: contentType });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;

    const revokeUrl = () => URL.revokeObjectURL(url);
    const done = () => {
      if (currentAudio === audio) currentAudio = null;
      revokeUrl();
      resolve();
    };

    try {
      const ctx = new AudioContext();
      currentAudioCtx = ctx;
      const src = ctx.createMediaElementSource(audio);
      const gain = ctx.createGain();
      gain.gain.value = GAIN;
      src.connect(gain);
      gain.connect(ctx.destination);
      audio.onended = () => {
        ctx.close().catch(() => {});
        if (currentAudioCtx === ctx) currentAudioCtx = null;
        done();
      };
      audio.onerror = () => {
        ctx.close().catch(() => {});
        if (currentAudioCtx === ctx) currentAudioCtx = null;
        done();
      };
      // iOS Safari requires AudioContext.resume() after creation before any playback.
      void ctx.resume().then(() => audio.play()).catch(() => { revokeUrl(); done(); });
    } catch {
      audio.onended = done;
      audio.onerror = done;
      void audio.play().catch(() => { revokeUrl(); done(); });
    }
  });
}

export function playBase64Audio(base64: string, contentType: string): Promise<void> {
  stopMomoSpeech();
  return _playOneChunk(base64, contentType);
}

export async function playMomoReply(
  text: string,
  synth: Pick<SynthesizeResponse, "audio_base64" | "content_type" | "is_mock">,
): Promise<void> {
  if (synth.audio_base64 && !synth.is_mock) {
    await playBase64Audio(synth.audio_base64, synth.content_type);
    return;
  }
  await speakWithBrowser(text);
}

// ── Streaming audio queue ──────────────────────────────────────────────────
// Uses a generation counter so stopAudioQueue() instantly invalidates
// all pending chunks without needing to cancel promises.

let _queueGen = 0;
let _tail: Promise<void> = Promise.resolve();
let _hadRealAudio = false;

export function enqueueAudio(base64: string, contentType: string, isMock: boolean): void {
  if (!base64 || isMock) return;
  _hadRealAudio = true;
  const myGen = _queueGen;
  _tail = _tail.then(async () => {
    if (_queueGen !== myGen) return;
    await _playOneChunk(base64, contentType);
  });
}

/** Resolves when all currently-enqueued audio has finished playing. */
export function whenQueueDone(): Promise<void> {
  return _tail;
}

export function hadRealAudio(): boolean {
  return _hadRealAudio;
}

export function stopAudioQueue(): void {
  _queueGen++;
  _tail = Promise.resolve();
  _hadRealAudio = false;
  stopMomoSpeech();
}
