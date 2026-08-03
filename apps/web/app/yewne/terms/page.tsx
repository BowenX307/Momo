import Link from "next/link";

import { TERMS_PARAGRAPHS, TERMS_TITLE, TERMS_VERSION } from "@/lib/legal/terms";

/**
 * /yewne/terms —— 用户协议全文页。
 *
 * 之前协议只在登录弹层的 TermsNotice 里可展开，而产品支持不登录直接聊天，
 * 那部分用户没有任何途径读到协议；菜单里的「服务条款 · 隐私政策」当时还是一行
 * 纯文字，点不动。这个页面就是给那条链接一个落点。
 *
 * 正文同样取自 lib/legal/terms.ts，与登录弹层共用一份，避免两处文案漂移。
 * 要改文案先改 docs/ 下的 docx，再重新提取，不要在这里手改。
 */

export const metadata = {
  title: `${TERMS_TITLE} · 于你 Yewne`,
  description: "于你 Yewne Alpha 测试用户协议全文。",
};

/** Heading1（"一、协议范围与定义"）与 Heading2（"1.1 协议范围"）的形态。 */
const H1_RE = /^[一二三四五六七八九十]+、/;
const H2_RE = /^\d+\.\d+\s/;

export default function TermsPage() {
  return (
    <div className="min-h-dvh w-full bg-[#f0e7d6] text-stone-800">
      <div className="mx-auto max-w-2xl px-6 py-12 sm:py-16">
        <Link
          href="/yewne"
          className="text-sm text-stone-500 transition-colors hover:text-stone-800"
        >
          ← 返回
        </Link>

        <h1 className="mt-8 text-2xl font-semibold leading-snug sm:text-3xl">
          {TERMS_TITLE}
        </h1>
        <p className="mt-2 text-sm text-stone-500">版本 {TERMS_VERSION}</p>

        <div className="mt-10">
          {TERMS_PARAGRAPHS.map((paragraph, i) => {
            // 首段是 "YEWNE · ALPHA TEST" 眉标、次段与标题重复，页头已经呈现过。
            if (i < 2) return null;

            if (H1_RE.test(paragraph)) {
              return (
                <h2 key={i} className="mt-10 mb-3 text-lg font-semibold sm:text-xl">
                  {paragraph}
                </h2>
              );
            }
            if (H2_RE.test(paragraph)) {
              return (
                <h3 key={i} className="mt-6 mb-2 font-semibold text-stone-700">
                  {paragraph}
                </h3>
              );
            }
            return (
              <p key={i} className="mb-3 text-[15px] leading-7 text-stone-700">
                {paragraph}
              </p>
            );
          })}
        </div>
      </div>
    </div>
  );
}
