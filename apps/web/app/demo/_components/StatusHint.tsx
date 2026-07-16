"use client";

/**
 * 在 AI 文字下方显示的柔和小字提示。
 *
 * 设计原则：
 * - 不弹窗、不闪烁，只是一行小字，不抢主回复的注意力；
 * - 危机命中：橙色调，引导现实支持（与后端 safety 文案语气一致）；
 * - degraded：蓝灰，告诉用户"目前是本地兜底"，不让 ta 误以为是真模型；
 * - 错误：红灰，简短描述，避免技术细节吓到用户。
 */

import type { SafetyFlag } from "@/lib/api/yewne";

type Variant = "crisis" | "degraded" | "error" | null;

interface Props {
  safetyFlag?: SafetyFlag;
  degraded?: boolean;
  error?: string | null;
}

function pickVariant({ safetyFlag, degraded, error }: Props): Variant {
  if (error) return "error";
  if (safetyFlag === "crisis_keyword") return "crisis";
  if (degraded) return "degraded";
  return null;
}

export function StatusHint(props: Props) {
  const variant = pickVariant(props);
  if (!variant) return null;

  if (variant === "crisis") {
    return (
      <p className="mt-3 text-center text-xs leading-relaxed text-amber-700 dark:text-amber-400">
        如果现在很难撑住，请联系一位你信任的人，
        <br />
        或拨打 24 小时心理援助热线 400-161-9995。
      </p>
    );
  }

  if (variant === "degraded") {
    return (
      <p className="mt-3 text-center text-xs leading-relaxed text-stone-500 dark:text-stone-400">
        现在是本地兜底回复，外部模型暂时联系不上。
      </p>
    );
  }

  return (
    <p className="mt-3 text-center text-xs leading-relaxed text-rose-600 dark:text-rose-400">
      {props.error ?? "出了点小问题，稍后再试一下。"}
    </p>
  );
}
