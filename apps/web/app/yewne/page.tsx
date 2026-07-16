import Image from "next/image";
import Link from "next/link";

import { Menu } from "./_components/Menu";

/**
 * /yewne —— 招商 / 展示 landing page。
 *
 * 视觉签名:蜡笔手绘 × 考究版式。hero 讲一个情绪:
 * "那些没说出口的" → 安静的于你接住它 → 于你在。
 *
 * 设计原则:光滑的于你小人 = 在场;潦草的蜡笔字 = 没说出口的真实情绪。
 * 反差本身就是意义。中文蜡笔感用 Google 手写体字体直接渲染,零素材。
 */

export default function YewneLanding() {
  return (
    <div className="relative min-h-dvh w-full overflow-x-hidden bg-[#f0e7d6] text-stone-800">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&family=Caveat:wght@600;700&family=Source+Serif+4:wght@400;500&display=swap');

        .font-hand   { font-family: 'ZCOOL KuaiLe', cursive; }
        .font-yewne    { font-family: 'Caveat', cursive; }
        .font-claude { font-family: 'Source Serif 4', Georgia, serif; }

        @keyframes yewne-heart {
          0%, 100% { opacity: .35; transform: scale(1); }
          50%      { opacity: .7;  transform: scale(1.15); }
        }
        @keyframes yewne-rise {
          from { opacity: 0; transform: translateY(14px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .yewne-rise { animation: yewne-rise 900ms cubic-bezier(0.16,1,0.3,1) both; }
        @keyframes yewne-fade { from { opacity: 0; } to { opacity: 1; } }
        .yewne-fade { animation: yewne-fade 240ms ease-out both; }
        .yewne-heart-glow { animation: yewne-heart 3.5s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .yewne-rise { animation: none; opacity: 1; transform: none; }
          .yewne-heart-glow { animation: none; opacity: .5; }
        }
      `}</style>

      {/* 纸张颗粒:贴合蜡笔图的纸纹 */}
      <div
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.5' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.7'/%3E%3C/svg%3E\")",
          backgroundSize: "200px 200px",
          opacity: 0.5,
          mixBlendMode: "multiply",
        }}
      />
      {/* 蜡笔手绘滤镜:用噪声把平滑的字/线边缘打毛,做出手绘糙边质感 */}
      <svg className="absolute h-0 w-0" aria-hidden>
        <defs>
          <filter id="crayon">
            <feTurbulence type="fractalNoise" baseFrequency="0.06" numOctaves="3" seed="7" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="3.6" xChannelSelector="R" yChannelSelector="G" />
          </filter>
          {/* 细 UI 线用:更细的抖动、更小位移,免得把细线打散 */}
          <filter id="crayon-soft">
            <feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="2" seed="4" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="1.6" xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </defs>
      </svg>

      {/* 左上角菜单 */}
      <Menu />

      <main className="relative z-10">
        {/* Hero */}
        <section className="relative flex min-h-dvh flex-col items-center justify-center px-6 py-16">
        {/* 角色:光滑的"在场",心口柔光脉动 */}
        <div className="relative w-[260px] max-w-[70vw] sm:w-[320px]">
          <div
            className="relative"
            style={{
              // 圆角矩形淡化:一个带高斯模糊的圆角矩形当遮罩,四边羽化、四角自然圆润。
              WebkitMaskImage:
                "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 100' preserveAspectRatio='none'%3E%3Cfilter id='f' x='-40%25' y='-40%25' width='180%25' height='180%25'%3E%3CfeGaussianBlur stdDeviation='8'/%3E%3C/filter%3E%3Crect x='19' y='15' width='43' height='78' rx='18' fill='%23fff' filter='url(%23f)'/%3E%3C/svg%3E\")",
              WebkitMaskSize: "100% 100%",
              WebkitMaskRepeat: "no-repeat",
              maskImage:
                "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 100' preserveAspectRatio='none'%3E%3Cfilter id='f' x='-40%25' y='-40%25' width='180%25' height='180%25'%3E%3CfeGaussianBlur stdDeviation='8'/%3E%3C/filter%3E%3Crect x='19' y='15' width='43' height='78' rx='18' fill='%23fff' filter='url(%23f)'/%3E%3C/svg%3E\")",
              maskSize: "100% 100%",
              maskRepeat: "no-repeat",
            }}
          >
            <Image
              src="/yewne/yewne-crayon-2.png"
              alt="于你"
              width={819}
              height={1024}
              priority
              className="h-auto w-full select-none"
            />
          </div>
          {/* 心口柔光 */}
          <span
            className="yewne-heart-glow pointer-events-none absolute h-16 w-16 rounded-full"
            style={{
              left: "54%",
              top: "58%",
              transform: "translate(-50%, -50%)",
              background:
                "radial-gradient(circle, rgba(214,110,118,0.55) 0%, rgba(214,110,118,0) 70%)",
            }}
          />
        </div>

        {/* 情绪标题:让 hero 有信息 */}
        <h1
          className="yewne-rise mt-9 font-hand text-balance text-center text-[32px] leading-snug text-[#504437]/75 sm:text-[40px]"
          style={{ animationDelay: "500ms", filter: "url(#crayon)" }}
        >
          那些没说出口的，<span className="font-yewne text-[#d66e76]/90">Yewne</span> 都在。
        </h1>

        {/* CTA:外层做入场动画,内层 Link 控制静止透明度(父子 opacity 相乘) */}
        <div className="yewne-rise mt-5" style={{ animationDelay: "900ms" }}>
          <Link
            href="/yewne/chat"
            className="group font-hand relative inline-flex flex-col items-center text-[26px] text-[#504437] opacity-70 transition hover:text-[#c2555e] hover:opacity-100"
            style={{ filter: "url(#crayon)" }}
          >
            <span>和它说句话</span>
            <svg
              className="mt-1 h-[12px] w-[92%]"
              viewBox="0 0 200 12"
              preserveAspectRatio="none"
              fill="none"
              aria-hidden
            >
              <path
                d="M3 7 Q 40 2 80 6 T 150 6 T 197 5"
                className="stroke-[#504437] transition-colors group-hover:stroke-[#d66e76]"
                strokeWidth="3.5"
                strokeLinecap="round"
              />
            </svg>
          </Link>
        </div>
        </section>

      </main>
    </div>
  );
}
