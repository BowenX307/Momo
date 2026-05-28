import type { HistoryMessage, Scene } from "@/lib/api/momo";

const KEY = "momo:session";
const TTL_MS = 24 * 60 * 60 * 1000;
const MAX_TURNS = 10;
const MAX_MSG_LEN = 500;

export interface ConvTurn {
  userText: string;
  reply: string;
}

export interface PersistedSession {
  history: HistoryMessage[];
  scene: Scene | null;
  turns: ConvTurn[];
  savedAt: number;
}

export function loadSession(): PersistedSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as PersistedSession;
    if (Date.now() - session.savedAt > TTL_MS) {
      localStorage.removeItem(KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function saveSession(session: PersistedSession): void {
  if (typeof window === "undefined") return;
  try {
    const trimmedHistory = session.history.slice(-MAX_TURNS * 2).map((m) => ({
      ...m,
      content: m.content.slice(0, MAX_MSG_LEN),
    }));
    const trimmedTurns = session.turns.slice(-MAX_TURNS).map((t) => ({
      userText: t.userText.slice(0, MAX_MSG_LEN),
      reply: t.reply.slice(0, MAX_MSG_LEN),
    }));
    localStorage.setItem(
      KEY,
      JSON.stringify({ ...session, history: trimmedHistory, turns: trimmedTurns }),
    );
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(KEY);
}

export function formatRelativeTime(savedAt: number): string {
  const diffMs = Date.now() - savedAt;
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}小时前`;
  return `${Math.floor(hours / 24)}天前`;
}
