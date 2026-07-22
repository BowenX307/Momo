import type { HistoryMessage, Persona, Scene } from "@/lib/api/yewne";

// 会话按人格分键存储，切换人格时各自保留历史。
const KEY_PREFIX = "yewne:session:";
const USER_ID_KEY = "yewne:external-user-id";
const TTL_MS = 24 * 60 * 60 * 1000;
const MAX_TURNS = 10;
const MAX_MSG_LEN = 500;

function keyFor(persona: Persona): string {
  return `${KEY_PREFIX}${persona}`;
}

export interface ConvTurn {
  userText: string;
  reply: string;
}

export interface PersistedSession {
  history: HistoryMessage[];
  scene: Scene | null;
  conversationId: string | null;
  turns: ConvTurn[];
  savedAt: number;
}

export type SessionSnapshot = Omit<PersistedSession, "savedAt">;

export function getOrCreateExternalUserId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = localStorage.getItem(USER_ID_KEY);
    if (existing) return existing;

    const generated = crypto.randomUUID();
    localStorage.setItem(USER_ID_KEY, generated);
    return generated;
  } catch {
    return crypto.randomUUID();
  }
}

export function loadSession(persona: Persona): PersistedSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(keyFor(persona));
    if (!raw) return null;
    const session = JSON.parse(raw) as PersistedSession;
    if (Date.now() - session.savedAt > TTL_MS) {
      localStorage.removeItem(keyFor(persona));
      return null;
    }
    return {
      ...session,
      conversationId: session.conversationId ?? null,
    };
  } catch {
    return null;
  }
}

export function saveSession(persona: Persona, session: SessionSnapshot): void {
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
      keyFor(persona),
      JSON.stringify({
        ...session,
        history: trimmedHistory,
        turns: trimmedTurns,
        savedAt: Date.now(),
      }),
    );
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function clearSession(persona: Persona): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(keyFor(persona));
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
