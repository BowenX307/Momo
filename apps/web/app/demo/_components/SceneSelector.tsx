"use client";

/**
 * 场景选择器：用第一人称小字代替干硬枚举名，更"陪伴"。
 *
 * 视觉刻意做成"小字 + 圆点"，不像 button 像 link，避免选择本身造成压力。
 * 选中项加深、左侧圆点变实心。
 */

import type { Scene } from "@/lib/api/momo";

interface Option {
  scene: Scene;
  label: string;
}

const OPTIONS: Option[] = [
  { scene: "late_night", label: "今晚有些事压在心里" },
  { scene: "rumination", label: "脑子里反复想一件事" },
  { scene: "relationship", label: "和谁的关系卡住了" },
  { scene: "stress", label: "撑不住、想喘口气" },
  { scene: "loneliness", label: "现在没人可以说话" },
];

interface Props {
  value: Scene;
  onChange: (scene: Scene) => void;
  disabled?: boolean;
}

export function SceneSelector({ value, onChange, disabled }: Props) {
  return (
    <ul className="flex flex-col gap-1.5 text-sm">
      {OPTIONS.map((opt) => {
        const selected = opt.scene === value;
        return (
          <li key={opt.scene}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(opt.scene)}
              aria-pressed={selected}
              className={[
                "group flex w-full items-center gap-2.5 rounded-md px-2 py-1 text-left transition-colors",
                "disabled:cursor-not-allowed disabled:opacity-60",
                selected
                  ? "text-violet-700 dark:text-violet-300"
                  : "text-zinc-500 hover:text-zinc-800 dark:text-zinc-500 dark:hover:text-zinc-200",
              ].join(" ")}
            >
              <span
                aria-hidden="true"
                className={[
                  "h-1.5 w-1.5 shrink-0 rounded-full transition-all",
                  selected
                    ? "bg-violet-500 ring-2 ring-violet-200 dark:ring-violet-900"
                    : "bg-zinc-300 group-hover:bg-zinc-500 dark:bg-zinc-700",
                ].join(" ")}
              />
              <span>{opt.label}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
