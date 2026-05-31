/** 播放 MOMO 语音回复；mock 时降级到浏览器 speechSynthesis。 */

import type { SynthesizeResponse } from "@/lib/api/momo";

let currentAudio: HTMLAudioElement | null = null;

// Shared AudioContext pre-unlocked during a user gesture so subsequent
// programmatic playback is allowed on iOS/Android.
let _sharedCtx: AudioContext | null = null;

export function unlockAudio(): void {
  try {
    if (!_sharedCtx || _sharedCtx.state === "closed") {
      _sharedCtx = new AudioContext();
    }
    void _sharedCtx.resume();
  } catch { /* ignore */ }
}

export function stopMomoSpeech(): void {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
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


function _playOneChunk(base64: string, contentType: string): Promise<void> {
  return new Promise((resolve) => {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: contentType });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;

    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      clearTimeout(failsafe);
      if (currentAudio === audio) currentAudio = null;
      URL.revokeObjectURL(url);
      resolve();
    };

    // Safety net: resolve even if browser never fires audio events (common on mobile).
    const failsafe = setTimeout(done, 15_000);

    audio.onended = done;
    audio.onerror = done;
    // Avoid routing through AudioContext — createMediaElementSource causes onended
    // to fire before audio finishes coming out of the speaker on mobile.
    void audio.play().catch(done);
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
