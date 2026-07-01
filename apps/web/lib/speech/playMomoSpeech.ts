/** 播放 MOMO 语音回复；mock 时降级到浏览器 speechSynthesis。 */

import type { SynthesizeResponse } from "@/lib/api/momo";

// One reusable <audio> element, unlocked once inside a user gesture and then
// reused (src swapped) for every chunk. This is the reliable iOS pattern:
//  - HTMLAudioElement is "media" playback, so it survives the silent/ringer
//    switch (Web Audio does NOT — it gets muted by the hardware switch);
//  - once unlocked in a gesture, later programmatic play() is allowed;
//  - it doesn't auto-suspend the way an AudioContext does between gesture and
//    playback, so streaming chunks after the first don't get silently dropped.
let _el: HTMLAudioElement | null = null;
let _elTeardown: (() => void) | null = null;

// Built lazily: a short silent WAV used only to unlock the element in-gesture.
let _silentUrl: string | null = null;

function _ensureEl(): HTMLAudioElement {
  if (!_el) {
    _el = new Audio();
    _el.setAttribute("playsinline", "");
    _el.preload = "auto";
  }
  return _el;
}

function _silentWavUrl(): string {
  if (_silentUrl) return _silentUrl;
  const sampleRate = 8000;
  const samples = 800; // ~0.1s
  const buf = new ArrayBuffer(44 + samples);
  const v = new DataView(buf);
  const w = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i));
  };
  w(0, "RIFF"); v.setUint32(4, 36 + samples, true); w(8, "WAVE");
  w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate, true); v.setUint16(32, 1, true);
  v.setUint16(34, 8, true); w(36, "data"); v.setUint32(40, samples, true);
  for (let i = 0; i < samples; i++) v.setUint8(44 + i, 128); // 8-bit silence
  _silentUrl = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
  return _silentUrl;
}

export function unlockAudio(): void {
  try {
    const el = _ensureEl();
    // Play a tiny silent clip inside the gesture so later programmatic src
    // swaps + play() are allowed, and so playback survives the getUserMedia
    // (recording) audio-session switch on iOS.
    el.src = _silentWavUrl();
    void el.play().catch(() => {});
  } catch { /* ignore */ }
}

export function stopMomoSpeech(): void {
  if (_elTeardown) {
    _elTeardown();
    _elTeardown = null;
  }
  if (_el) {
    try { _el.pause(); } catch { /* noop */ }
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
    const el = _ensureEl();

    // Tear down any listeners left by a previous (interrupted) chunk on this
    // shared element before wiring up our own.
    if (_elTeardown) { _elTeardown(); _elTeardown = null; }

    let settled = false;
    let playStartedAt = 0;
    let durationMs = 0;

    const onMeta = () => { durationMs = (el.duration || 0) * 1000; };
    const onPlay = () => { playStartedAt = Date.now(); };

    const cleanup = () => {
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("play", onPlay);
      el.onended = null;
      el.onerror = null;
      clearTimeout(failsafe);
      setTimeout(() => URL.revokeObjectURL(url), 500);
    };

    const done = () => {
      if (settled) return;
      settled = true;
      if (_elTeardown === done) _elTeardown = null;
      cleanup();
      resolve();
    };

    const failsafe = setTimeout(done, 15_000);
    // If a later chunk or stopMomoSpeech reuses the element, this resolves the
    // current chunk's promise cleanly instead of leaving it hanging.
    _elTeardown = done;

    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("play", onPlay);
    el.onended = () => {
      // iOS/Safari fires onended when the buffer is exhausted, before audio has
      // fully come out of the speaker. If we haven't reached the expected
      // duration yet, wait out the remainder before resolving.
      if (playStartedAt > 0 && durationMs > 100) {
        const elapsed = Date.now() - playStartedAt;
        const remaining = durationMs - elapsed + 150;
        if (remaining > 80) {
          setTimeout(done, remaining);
          return;
        }
      }
      done();
    };
    el.onerror = done;

    el.src = url;
    el.load();
    void el.play().catch(done);
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

export function enqueueAudio(
  base64: string,
  contentType: string,
  isMock: boolean,
  onStart?: () => void,
): void {
  if (!base64 || isMock) return;
  _hadRealAudio = true;
  const myGen = _queueGen;
  _tail = _tail.then(async () => {
    if (_queueGen !== myGen) return;
    // 在这句音频真正开始播放的时刻触发，用于同步显示对应文字。
    onStart?.();
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
