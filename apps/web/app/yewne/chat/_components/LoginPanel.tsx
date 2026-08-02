"use client";

/**
 * 登录 / 注册弹层。视觉沿用 /yewne/chat 页面的蜡笔纸感(依赖同页面里定义的 #crayon-soft SVG 滤镜)。
 *
 * 四步:
 *   phone     填手机号 + 勾协议 → 选「验证码登录」或「密码登录」
 *   code      验证码登录(注册也走这条:手机号没绑过人就当场注册)
 *   password  密码登录(只有设过密码的账号能用) → 可跳「忘记密码」
 *   reset     验证码 + 新密码,重置完直接登录
 *
 * 协议勾选放在第一步、按钮上方:不勾就两条登录路径都点不动。后端也会再校验一次
 * (agreed_to_terms)，前端 disabled 只是省一次往返，不是安全边界。
 */

import { useEffect, useRef, useState } from "react";

import {
  fetchLoginPassword,
  fetchResetPassword,
  fetchSendCode,
  fetchVerifyCode,
  YewneApiError,
  type AuthApiErrorBody,
  type VerifyCodeResponse,
} from "@/lib/api/yewne";

import { TermsNotice } from "./TermsNotice";

const PHONE_RE = /^1[3-9]\d{9}$/;
const RESEND_COOLDOWN_SECONDS = 60;
const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_MAX_LENGTH = 64;

type Step = "phone" | "code" | "password" | "reset";

function errorMessage(err: unknown): string {
  if (err instanceof YewneApiError) {
    const body = err.body as AuthApiErrorBody | undefined;
    if (body?.code === "daily_limit") return "今天这个手机号发送次数到上限了，明天再试试。";
    if (body?.code === "cooldown") return "发送太频繁，等一下再点。";
    if (body?.code === "sms_failed") return "短信发送失败，晚点再试试。";
    if (body?.code === "invalid_code") return "验证码不对，或者已经过期了。";
    // 后端故意不区分"没注册"和"密码错"(防手机号枚举)，前端文案也要跟着含糊。
    if (body?.code === "invalid_credentials") return "手机号或密码不对。";
    if (body?.code === "too_many_attempts")
      return "密码错得太多次了，等一会儿再试，或者用验证码登录。";
    if (body?.code === "weak_password")
      return `密码要 ${PASSWORD_MIN_LENGTH}-${PASSWORD_MAX_LENGTH} 位，且不能全是数字。`;
    if (body?.code === "terms_required") return "要先同意用户协议才能继续。";
    if (body?.message) return body.message;
    return `请求失败（${err.status ?? "网络"}）`;
  }
  return "出错了，晚点再试试。";
}

/** 和后端 schemas.py 的 _validate_password 保持一致；不一致只会多一次白跑的请求。 */
function localPasswordProblem(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH || password.length > PASSWORD_MAX_LENGTH) {
    return `密码要 ${PASSWORD_MIN_LENGTH}-${PASSWORD_MAX_LENGTH} 位。`;
  }
  if (/^\d+$/.test(password)) return "密码不能全是数字。";
  return null;
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

const INPUT_CLASS =
  "rounded-xl border border-[#e3d8c2] bg-white px-4 py-2.5 font-hand text-lg text-[#504437] outline-none placeholder:text-[#504437]/35";
const PRIMARY_BUTTON_CLASS =
  "rounded-xl bg-[#d66e76] px-4 py-2.5 font-hand text-lg text-white transition-colors hover:bg-[#c2555e] disabled:cursor-not-allowed disabled:opacity-60";
const SUBTLE_BUTTON_CLASS =
  "font-hand text-sm text-[#504437]/55 underline decoration-dotted transition-colors hover:text-[#d66e76] disabled:no-underline disabled:opacity-50";

export function LoginPanel({ externalUserId, onClose, onSuccess }: LoginPanelProps) {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
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

  function finish(res: VerifyCodeResponse) {
    onSuccess({
      token: res.token,
      externalUserId: res.external_user_id,
      phoneNumber: phone,
      expiresInSeconds: res.expires_in_seconds,
    });
  }

  /** 统一包住 loading / 错误处理，省得每个 handler 都写一遍 try-finally。 */
  async function run(action: () => Promise<void>) {
    setError(null);
    setLoading(true);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function phoneIsValid(): boolean {
    if (!PHONE_RE.test(phone)) {
      setError("手机号格式不对，检查一下。");
      return false;
    }
    return true;
  }

  function handleSendCode(purpose: "login" | "reset", nextStep: Step) {
    if (!phoneIsValid()) return;
    void run(async () => {
      await fetchSendCode(phone, { purpose });
      setStep(nextStep);
      startCooldown();
    });
  }

  function handleGoPasswordStep() {
    if (!phoneIsValid()) return;
    setError(null);
    setStep("password");
  }

  function handleVerifyCode() {
    if (code.trim().length < 4) {
      setError("验证码填完整。");
      return;
    }
    void run(async () => finish(await fetchVerifyCode(phone, code.trim(), externalUserId, agreed)));
  }

  function handlePasswordLogin() {
    if (!password) {
      setError("填一下密码。");
      return;
    }
    void run(async () =>
      finish(await fetchLoginPassword(phone, password, externalUserId, agreed)),
    );
  }

  function handleResetPassword() {
    if (code.trim().length < 4) {
      setError("验证码填完整。");
      return;
    }
    const problem = localPasswordProblem(newPassword);
    if (problem) {
      setError(problem);
      return;
    }
    void run(async () =>
      finish(
        await fetchResetPassword(phone, code.trim(), newPassword, externalUserId, agreed),
      ),
    );
  }

  function backToPhone() {
    setStep("phone");
    setError(null);
    setCode("");
    setPassword("");
    setNewPassword("");
  }

  const subtitle = {
    phone: "手机号登录，历史消息不会丢。",
    code: `验证码发到 ${phone} 了`,
    password: "用密码登录",
    reset: `重置密码，验证码发到 ${phone} 了`,
  }[step];

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
        <p className="mt-1 font-hand text-sm text-[#504437]/55">{subtitle}</p>

        <div className="mt-5 flex flex-col gap-3">
          {step === "phone" && (
            <>
              <input
                type="tel"
                inputMode="numeric"
                value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
                placeholder="手机号"
                maxLength={11}
                className={INPUT_CLASS}
              />

              <TermsNotice checked={agreed} onChange={setAgreed} disabled={loading} />

              {error && <p className="font-hand text-sm text-[#c2555e]">{error}</p>}

              <button
                type="button"
                disabled={loading || !agreed}
                onClick={() => handleSendCode("login", "code")}
                className={PRIMARY_BUTTON_CLASS}
              >
                {loading ? "请稍等…" : "发送验证码"}
              </button>
              <button
                type="button"
                disabled={loading || !agreed}
                onClick={handleGoPasswordStep}
                className={SUBTLE_BUTTON_CLASS}
              >
                用密码登录
              </button>
            </>
          )}

          {step === "code" && (
            <>
              <input
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                placeholder="验证码"
                maxLength={8}
                className={`${INPUT_CLASS} tracking-widest`}
              />

              {error && <p className="font-hand text-sm text-[#c2555e]">{error}</p>}

              <button
                type="button"
                disabled={loading}
                onClick={handleVerifyCode}
                className={PRIMARY_BUTTON_CLASS}
              >
                {loading ? "请稍等…" : "登录"}
              </button>
              <button
                type="button"
                disabled={cooldown > 0 || loading}
                onClick={() => handleSendCode("login", "code")}
                className={SUBTLE_BUTTON_CLASS}
              >
                {cooldown > 0 ? `重新发送（${cooldown}s）` : "没收到？重新发送"}
              </button>
              <button type="button" onClick={backToPhone} className={SUBTLE_BUTTON_CLASS}>
                换个手机号
              </button>
            </>
          )}

          {step === "password" && (
            <>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="密码"
                maxLength={PASSWORD_MAX_LENGTH}
                className={INPUT_CLASS}
              />

              {error && <p className="font-hand text-sm text-[#c2555e]">{error}</p>}

              <button
                type="button"
                disabled={loading}
                onClick={handlePasswordLogin}
                className={PRIMARY_BUTTON_CLASS}
              >
                {loading ? "请稍等…" : "登录"}
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() => handleSendCode("reset", "reset")}
                className={SUBTLE_BUTTON_CLASS}
              >
                忘记密码？用验证码重置
              </button>
              <button type="button" onClick={backToPhone} className={SUBTLE_BUTTON_CLASS}>
                返回
              </button>
            </>
          )}

          {step === "reset" && (
            <>
              <input
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                placeholder="验证码"
                maxLength={8}
                className={`${INPUT_CLASS} tracking-widest`}
              />
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
                onClick={handleResetPassword}
                className={PRIMARY_BUTTON_CLASS}
              >
                {loading ? "请稍等…" : "重置并登录"}
              </button>
              <button
                type="button"
                disabled={cooldown > 0 || loading}
                onClick={() => handleSendCode("reset", "reset")}
                className={SUBTLE_BUTTON_CLASS}
              >
                {cooldown > 0 ? `重新发送（${cooldown}s）` : "没收到？重新发送"}
              </button>
              <button type="button" onClick={backToPhone} className={SUBTLE_BUTTON_CLASS}>
                返回
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
