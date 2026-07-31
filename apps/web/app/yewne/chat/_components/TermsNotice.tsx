"use client";

/**
 * 登录弹层里的「同意用户协议」勾选框 + 可展开的协议全文。
 *
 * 正文来自 lib/legal/terms.ts(从 docs/于你Yewne_Alpha测试用户协议_Alpha1.0.docx 提取)。
 * 协议第 2.2 条明确「仅限年满 18 周岁」且「即使取得监护人同意亦不例外」,所以勾选文案
 * 里带上年龄确认——这不是可选的礼貌措辞,是协议要求的准入条件。
 */

import { useState } from "react";

import { TERMS_PARAGRAPHS, TERMS_TITLE } from "@/lib/legal/terms";

interface TermsNoticeProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function TermsNotice({ checked, onChange, disabled }: TermsNoticeProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <label className="flex cursor-pointer items-start gap-2 font-hand text-sm text-[#504437]/70">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="mt-[3px] h-4 w-4 shrink-0 accent-[#d66e76]"
        />
        <span>
          我已年满 18 周岁，并已阅读同意
          <button
            type="button"
            onClick={(e) => {
              // 点链接只展开正文，不要顺带把勾选框切了
              e.preventDefault();
              setExpanded((v) => !v);
            }}
            className="mx-0.5 text-[#d66e76] underline decoration-dotted"
          >
            {TERMS_TITLE}
          </button>
        </span>
      </label>

      {expanded && (
        <div className="max-h-52 overflow-y-auto rounded-xl border border-[#e3d8c2] bg-white/60 px-3 py-2.5">
          {TERMS_PARAGRAPHS.map((paragraph, i) => (
            <p
              key={i}
              className="mb-1.5 font-hand text-xs leading-relaxed text-[#504437]/75 last:mb-0"
            >
              {paragraph}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
