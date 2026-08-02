"use client";

/**
 * 左上角汉堡菜单(两条线)→ 点开全屏菜单。
 * 背景纸张质感与主页一致;菜单文字用类 Claude 的衬线体(Source Serif 4)。
 * 菜单项暂为占位,之后替换成真实内容。
 */

import { useState } from "react";
import Link from "next/link";

const LINKS: { label: string; href: string }[] = [
  { label: "体验 Demo", href: "/demo" },
  { label: "关于于你", href: "#" },
  { label: "功能特性", href: "#" },
  { label: "团队", href: "#" },
  { label: "联系我们", href: "#" },
];

const SOCIALS = ["小红书", "微博", "微信公众号"];

// 与主页一致的纸张颗粒纹理
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.5' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.7'/%3E%3C/svg%3E\")";

export function Menu() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* 汉堡按钮:两条蜡笔糙边的线 */}
      <button
        type="button"
        aria-label="打开菜单"
        onClick={() => setOpen(true)}
        className="absolute left-6 top-6 z-40 flex h-10 w-10 flex-col items-center justify-center gap-[7px]"
        style={{ filter: "url(#crayon-soft)" }}
      >
        <span className="h-[3px] w-7 rounded-full bg-[#504437]" />
        <span className="h-[3px] w-[26px] rounded-full bg-[#504437]" />
      </button>

      {/* 全屏菜单 */}
      {open && (
        <div className="yewne-fade fixed inset-0 z-50 bg-[#f0e7d6]">
          {/* 纸张颗粒 */}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage: GRAIN,
              backgroundSize: "200px 200px",
              opacity: 0.5,
              mixBlendMode: "multiply",
            }}
          />

          {/* 关闭按钮 */}
          <button
            type="button"
            aria-label="关闭菜单"
            onClick={() => setOpen(false)}
            className="absolute left-6 top-6 z-20 flex h-10 w-10 items-center justify-center text-[#504437]"
            style={{ filter: "url(#crayon-soft)" }}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <line x1="6" y1="6" x2="18" y2="18" />
              <line x1="18" y1="6" x2="6" y2="18" />
            </svg>
          </button>

          <nav className="font-claude relative z-10 flex h-full flex-col px-8 pb-10 pt-28 sm:px-12">
            <div className="flex flex-col gap-5">
              {LINKS.map((l) => (
                <Link
                  key={l.label}
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="text-3xl text-stone-800 transition-colors hover:text-[#c66645] sm:text-4xl"
                >
                  {l.label}
                </Link>
              ))}
            </div>

            <div className="mt-10 flex flex-col gap-2">
              {SOCIALS.map((s) => (
                <a key={s} href="#" className="text-lg text-stone-600 transition-colors hover:text-stone-800">
                  {s}
                </a>
              ))}
            </div>

            {/* 合成一个链接而不是分成"服务条款·隐私政策"两条：目前只有《Alpha 测试
                用户协议》一份文档，没有独立的隐私政策。这份协议里确有实质的个人信息
                条款（第五节「对话数据与个人信息保护」、第十四节「投诉、申诉与联系
                我们」），所以叫「用户协议与隐私条款」是准确的；写成「隐私政策」则会
                指向一份不存在的文件。独立隐私政策成文后再拆成两条。 */}
            <div className="mt-auto pt-10 text-sm text-stone-500">
              <Link
                href="/yewne/terms"
                onClick={() => setOpen(false)}
                className="underline decoration-dotted underline-offset-4 transition-colors hover:text-stone-800"
              >
                用户协议与隐私条款
              </Link>
            </div>
          </nav>
        </div>
      )}
    </>
  );
}
