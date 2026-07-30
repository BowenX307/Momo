"use client";

/**
 * 手机号 + 验证码登录弹层。两步:填手机号发验证码 -> 填验证码登录。
 * 视觉沿用 /yewne/chat 页面的蜡笔纸感(依赖同页面里定义的 #crayon-soft SVG 滤镜)。
 */

import { useEffect, useRef, useState } from "react";

import {
  fetchSendCode,
  fetchVerifyCode,
  YewneApiError,
  type AuthApiErrorBody,
} from "@/lib/api/yewne";

const PHONE_RE = /^1[3-9]\d{9}$/;
const RESEND_COOLDOWN_SECONDS = 60;

function errorMessage(err: unknown): string {
  if (err instanceof YewneApiError) {
    const body = err.body as AuthApiErrorBody | undefined;
    if (body?.code === "daily_limit") return "今天这个手机号发送次数到上限了，明天再试试。";
    if (body?.code === "cooldown") return "发送太频繁，等一下再点。";
    if (body?.code === "sms_failed") return "短信发送失败，晚点再试试。";
    if (body?.code === "invalid_code") return "验证码不对，或者已经过期了。";
    if (body?.message) return body.message;
    return `请求失败（${err.status ?? "网络"}）`;
  }
  return "出错了，晚点再试试。";
}

interface LoginPanelProps {
  externalUserId: string;
  onClose: () => void;
  onSuccess: (result: {
    token: string;
    externalUserId: string;
    phoneNumber: string;
    expiresInSeconds: number;
  }) => void;
}

export function LoginPanel({ externalUserId, onClose, onSuccess }: LoginPanelProps) {
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const cooldownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (cooldownTimerRef.current) clearInterval(cooldownTimerRef.current);
    };
  }, []);

  function startCooldown() {
    setCooldown(RESEND_COOLDOWN_SECONDS);
    if (cooldownTimerRef.current) clearInterval(cooldownTimerRef.current);
    cooldownTimerRef.current = setInterval(() => {
      setCooldown((c) => {
        if (c <= 1) {
          if (cooldownTimerRef.current) clearInterval(cooldownTimerRef.current);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }

  async function handleSendCode() {
    if (!PHONE_RE.test(phone)) {
      setError("手机号格式不对，检查一下。");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await fetchSendCode(phone);
      setStep("code");
      startCooldown();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleVerify() {
    if (code.trim().length < 4) {
      setError("验证码填完整。");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetchVerifyCode(phone, code.trim(), externalUserId);
      onSuccess({
        token: res.token,
        externalUserId: res.external_user_id,
        phoneNumber: phone,
        expiresInSeconds: res.expires_in_seconds,
      });
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
          登录 / 注册
        </h2>
        <p className="mt-1 font-hand text-sm text-[#504437]/55">
          {step === "phone" ? "手机号登录，历史消息不会丢。" : `验证码发到 ${phone} 了`}
        </p>

        <div className="mt-5 flex flex-col gap-3">
          {step === "phone" ? (
            <input
              type="tel"
              inputMode="numeric"
              value={phone}
              onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
              placeholder="手机号"
              maxLength={11}
              className="rounded-xl border border-[#e3d8c2] bg-white px-4 py-2.5 font-hand text-lg text-[#504437] outline-none placeholder:text-[#504437]/35"
            />
          ) : (
            <input
              type="text"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
              placeholder="验证码"
              maxLength={8}
              className="rounded-xl border border-[#e3d8c2] bg-white px-4 py-2.5 font-hand text-lg tracking-widest text-[#504437] outline-none placeholder:text-[#504437]/35"
            />
          )}

          {error && <p className="font-hand text-sm text-[#c2555e]">{error}</p>}

          <button
            type="button"
            disabled={loading}
            onClick={() => void (step === "phone" ? handleSendCode() : handleVerify())}
            className="rounded-xl bg-[#d66e76] px-4 py-2.5 font-hand text-lg text-white transition-colors hover:bg-[#c2555e] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "请稍等…" : step === "phone" ? "发送验证码" : "登录"}
          </button>

          {step === "code" && (
            <button
              type="button"
              disabled={cooldown > 0 || loading}
              onClick={() => void handleSendCode()}
              className="font-hand text-sm text-[#504437]/55 underline decoration-dotted disabled:no-underline disabled:opacity-50"
            >
              {cooldown > 0 ? `重新发送（${cooldown}s）` : "没收到？重新发送"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
