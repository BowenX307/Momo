import Image from "next/image";
import Link from "next/link";

import { Menu } from "./_components/Menu";
import { Reveal } from "./_components/Reveal";

/**
 * /uni —— 招商 / 展示 landing page。
 *
 * 视觉签名:蜡笔手绘 × 考究版式。hero 讲一个情绪:
 * "那些没说出口的" → 安静的 uni 接住它 → uni 在。
 *
 * 设计原则:光滑的 uni 小人 = 在场;潦草的蜡笔字 = 没说出口的真实情绪。
 * 反差本身就是意义。中文蜡笔感用 Google 手写体字体直接渲染,零素材。
 */

export default function UniLanding() {
  return (
    <div className="relative min-h-dvh w-full overflow-x-hidden bg-[#f0e7d6] text-stone-800">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&family=Caveat:wght@600;700&family=Source+Serif+4:wght@400;500&display=swap');

        .font-hand   { font-family: 'ZCOOL KuaiLe', cursive; }
        .font-uni    { font-family: 'Caveat', cursive; }
        .font-claude { font-family: 'Source Serif 4', Georgia, serif; }

        @keyframes uni-heart {
          0%, 100% { opacity: .35; transform: scale(1); }
          50%      { opacity: .7;  transform: scale(1.15); }
        }
        @keyframes uni-rise {
          from { opacity: 0; transform: translateY(14px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .uni-rise { animation: uni-rise 900ms cubic-bezier(0.16,1,0.3,1) both; }
        @keyframes uni-fade { from { opacity: 0; } to { opacity: 1; } }
        .uni-fade { animation: uni-fade 240ms ease-out both; }
        .uni-heart-glow { animation: uni-heart 3.5s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .uni-rise { animation: none; opacity: 1; transform: none; }
          .uni-heart-glow { animation: none; opacity: .5; }
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
              src="/uni/uni-crayon-2.png"
              alt="uni"
              width={819}
              height={1024}
              priority
              className="h-auto w-full select-none"
            />
          </div>
          {/* 心口柔光 */}
          <span
            className="uni-heart-glow pointer-events-none absolute h-16 w-16 rounded-full"
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
          className="uni-rise mt-9 font-hand text-balance text-center text-[32px] leading-snug text-[#504437]/75 sm:text-[40px]"
          style={{ animationDelay: "500ms", filter: "url(#crayon)" }}
        >
          那些没说出口的，<span className="font-uni text-[#d66e76]/90">uni</span> 都在。
        </h1>

        {/* CTA:外层做入场动画,内层 Link 控制静止透明度(父子 opacity 相乘) */}
        <div className="uni-rise mt-5" style={{ animationDelay: "900ms" }}>
          <Link
            href="/demo"
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

        {/* 信息段 1:像真人一样陪你说话(Tolan 式两栏 + 暖白纸卡,蜡笔风) */}
        <section className="relative mx-auto max-w-5xl px-6 py-28 sm:py-36">
          <div className="grid items-center gap-10 sm:grid-cols-2 sm:gap-16">
            <Reveal className="flex flex-col gap-5">
              <h2 className="font-hand text-3xl leading-snug text-[#504437] sm:text-4xl">
                像真人一样，
                <br />
                陪你说话
              </h2>
              <p className="font-hand text-lg leading-relaxed text-[#504437]/75">
                不是一问一答的机器。它用声音陪你，会停顿，也能被打断，像朋友一样把话接住。
              </p>
            </Reveal>

            <Reveal delay={150}>
              {/* 暖白纸卡:比底色更亮、更白,装一段真实对话 */}
              <div className="rounded-2xl bg-[#faf6ec] p-6 shadow-[0_10px_34px_rgba(120,100,70,0.10)] sm:p-7">
                <div className="flex flex-col gap-3 font-hand text-[#504437]">
                  <span className="max-w-[82%] self-end rounded-2xl rounded-br-md bg-[#efe7d6] px-4 py-2 text-base leading-relaxed">
                    最近好累，又不想跟谁说。
                  </span>
                  <span className="max-w-[86%] self-start rounded-2xl rounded-bl-md bg-[#f3ede0] px-4 py-2 text-base leading-relaxed">
                    嗯，那就先不说。我陪你坐一会儿。
                  </span>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        {/* 信息段 2:三个人格 —— 标题 + 三张交错的纸卡(内容各异,非雷同卡) */}
        <section className="relative mx-auto max-w-5xl px-6 py-24 sm:py-28">
          <Reveal>
            <h2 className="font-hand text-3xl leading-snug text-[#504437] sm:text-4xl">
              想要哪种陪伴，你说了算
            </h2>
            <p className="mt-4 max-w-xl font-hand text-lg leading-relaxed text-[#504437]/75">
              三个性格，住在你的小世界里。换一个，就像换一种被陪着的方式。
            </p>
          </Reveal>
          <div className="mt-12 grid gap-6 sm:grid-cols-3">
            <Reveal delay={120}>
              <div className="rounded-2xl bg-[#faf6ec] p-6 shadow-[0_10px_34px_rgba(120,100,70,0.10)]">
                <div className="font-uni text-3xl text-[#d66e76]">momo</div>
                <div className="mt-1 font-hand text-sm text-[#504437]/55">温柔派</div>
                <p className="mt-3 font-hand text-base leading-relaxed text-[#504437]/85">
                  不评判，稳稳接住你。
                </p>
              </div>
            </Reveal>
            <Reveal delay={220} className="sm:mt-8">
              <div className="rounded-2xl bg-[#faf6ec] p-6 shadow-[0_10px_34px_rgba(120,100,70,0.10)]">
                <div className="font-uni text-3xl text-[#d66e76]">iris</div>
                <div className="mt-1 font-hand text-sm text-[#504437]/55">直接派</div>
                <p className="mt-3 font-hand text-base leading-relaxed text-[#504437]/85">
                  不灌鸡汤，嘴硬心软。
                </p>
              </div>
            </Reveal>
            <Reveal delay={320} className="sm:mt-4">
              <div className="rounded-2xl bg-[#faf6ec] p-6 shadow-[0_10px_34px_rgba(120,100,70,0.10)]">
                <div className="font-uni text-3xl text-[#d66e76]">rocky</div>
                <div className="mt-1 font-hand text-sm text-[#504437]/55">行动派</div>
                <p className="mt-3 font-hand text-base leading-relaxed text-[#504437]/85">
                  把难题拆小，陪你迈第一步。
                </p>
              </div>
            </Reveal>
          </div>
        </section>

        {/* 信息段 3:专业背书 —— 居中一张引用卡。⚠️ 引用与署名是占位,必须换成真人真话 */}
        <section className="relative mx-auto max-w-3xl px-6 py-24 text-center sm:py-28">
          <Reveal>
            <h2 className="font-hand text-3xl leading-snug text-[#504437] sm:text-4xl">
              和专业的人一起做
            </h2>
            <p className="mx-auto mt-4 max-w-xl font-hand text-lg leading-relaxed text-[#504437]/75">
              uni 的陪伴方式，和专业心理咨询师一起打磨：知道什么时候接住，什么时候退一步，绝不替代治疗。
            </p>
            <div className="mx-auto mt-10 max-w-xl rounded-2xl bg-[#faf6ec] p-7 text-left shadow-[0_10px_34px_rgba(120,100,70,0.10)] sm:p-8">
              <p className="font-hand text-xl leading-relaxed text-[#504437]">
                （待填：心理咨询师对 uni 的一句背书。）
              </p>
              <div className="mt-4 font-hand text-sm text-[#504437]/60">
                （姓名 · 职称 · 机构）
              </div>
            </div>
          </Reveal>
        </section>

        {/* 信息段 4:研发 —— 文字为主的编辑式,顺带亮出"反光滑"的态度 */}
        <section className="relative mx-auto max-w-3xl px-6 py-24 sm:py-32">
          <Reveal className="flex flex-col gap-6">
            <h2 className="font-hand text-3xl leading-snug text-[#504437] sm:text-4xl">
              真正的功夫，在模型之上
            </h2>
            <p className="font-hand text-lg leading-relaxed text-[#504437]/80">
              我们站在最好的 AI 模型上，但难的从来不是模型。难的是我们加在上面的那一层：让 uni 怎么听、怎么回应、什么时候该打断，什么时候只是安静陪着。
            </p>
            <p className="font-hand text-lg leading-relaxed text-[#504437]/80">
              在一个越来越光滑的 AI 世界里，我们想做一个有手感、会克制、像人一样的陪伴。
            </p>
          </Reveal>
        </section>
      </main>
    </div>
  );
}
