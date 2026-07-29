// 登录态 token 持久化。token 本身是后端签发的服务端存储随机字符串（不是 JWT），
// 这里只负责本地存取，真正的有效期/撤销由后端 Redis 控制。

const TOKEN_KEY = "yewne:auth-token";
const PHONE_KEY = "yewne:auth-phone";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string, phoneNumber: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(PHONE_KEY, phoneNumber);
  } catch {
    // localStorage 不可用时，本次登录状态不会持久化，刷新后需要重新登录
  }
}

export function getStoredPhoneNumber(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(PHONE_KEY);
  } catch {
    return null;
  }
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(PHONE_KEY);
  } catch {
    // ignore
  }
}

/** 手机号打码显示，比如 138****9307。 */
export function maskPhoneNumber(phoneNumber: string): string {
  if (phoneNumber.length !== 11) return phoneNumber;
  return `${phoneNumber.slice(0, 3)}****${phoneNumber.slice(7)}`;
}
