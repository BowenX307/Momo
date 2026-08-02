"use client";

/**
 * 已登录状态下设置 / 修改密码的小弹层。视觉与 LoginPanel 一致。
 *
 * hasPassword 决定两件事:标题文案,以及要不要填当前密码。已经设过密码的必须验旧密码
 * (后端也会验,前端这层只是提前给提示);首次设置不用,因为持有有效 token 本身就是身份证明。
 */

import { useState } from "react";

import { fetchSetPassword, YewneApiError, type AuthApiErrorBody } from "@/lib/api/yewne";

const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_MAX_LENGTH = 64;

function errorMessage(err: unknown): string {
  if (err instanceof YewneApiError) {
    const body = err.body as AuthApiErrorBody | undefined;
    if (body?.code === "invalid_credentials") return "当前密码不对。";
    if (body?.code === "unauthorized") return "登录状态失效了，重新登录一下。";
    if (body?.code === "weak_password")
      return `密码要 ${PASSWORD_MIN_LENGTH}-${PASSWORD_MAX_LENGTH} 位，且不能全是数字。`;
    if (body?.message) return body.message;
    return `请求失败（${err.status ?? "网络"}）`;
  }
  return "出错了，晚点再试试。";
}

/** 和后端 schemas.py 的 _validate_password 保持一致。 */
function localPasswordProblem(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH || password.length > PASSWORD_MAX_LENGTH) {
    return `密码要 ${PASSWORD_MIN_LENGTH}-${PASSWORD_MAX_LENGTH} 位。`;
  }
  if (/^\d+$/.test(password)) return "密码不能全是数字。";
  return null;
}

const INPUT_CLASS =
  "rounded-xl border border-[#e3d8c2] bg-white px-4 py-2.5 font-hand text-lg text-[#504437] outline-none placeholder:text-[#504437]/35";

interface PasswordPanelProps {
  token: string;
  hasPassword: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function PasswordPanel({
  token,
  hasPassword,
  onClose,
  onSuccess,
}: PasswordPanelProps) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    if (hasPassword && !currentPassword) {
      setError("填一下当前密码。");
      return;
    }
    const problem = localPasswordProblem(newPassword);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await fetchSetPassword(token, hasPassword ? currentPassword : null, newPassword);
      onSuccess();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-6">
      <button
        type="button"
        aria-label="收起"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-[#3a2f26]/45 backdrop-blur-[2px]"
      />
      <div className="relative z-10 w-[380px] max-w-[90vw] rounded-2xl bg-[#fbf7ee] p-6 shadow-[0_22px_55px_rgba(60,45,30,0.4)]">
        <h2
          className="font-hand text-xl text-[#504437]"
          style={{ filter: "url(#crayon-soft)" }}
        >
          {hasPassword ? "修改密码" : "设置密码"}
        </h2>
        <p className="mt-1 font-hand text-sm text-[#504437]/55">
          设了密码，下次登录就不用等短信了。
        </p>

        <div className="mt-5 flex flex-col gap-3">
          {hasPassword && (
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="当前密码"
              maxLength={PASSWORD_MAX_LENGTH}
              className={INPUT_CLASS}
            />
          )}
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder={`新密码（${PASSWORD_MIN_LENGTH}-${PASSWORD_MAX_LENGTH} 位，不能全是数字）`}
            maxLength={PASSWORD_MAX_LENGTH}
            className={INPUT_CLASS}
          />

          {error && <p className="font-hand text-sm text-[#c2555e]">{error}</p>}

          <button
            type="button"
            disabled={loading}
            onClick={() => void handleSubmit()}
            className="rounded-xl bg-[#d66e76] px-4 py-2.5 font-hand text-lg text-white transition-colors hover:bg-[#c2555e] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "请稍等…" : hasPassword ? "确认修改" : "确认设置"}
          </button>
        </div>
      </div>
    </div>
  );
}
