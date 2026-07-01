"use client";

/**
 * 字墙:满屏重叠的"没说出口的话",密度爆炸,营造"被淹没"。
 * 纯文字、零素材。滚动进入视口时逐字累积浮现(像话一句句堆上来)。
 * 尊重 prefers-reduced-motion(直接全部显示)。
 *
 * 设计:墨色 rgba(80,68,55,*) 同色、靠透明度/尺度/角度变化;中心更重、边缘更淡;
 * "我没事 / 我可以的 / 我挺好的" 这种逞强的划掉。
 */

import { useEffect, useRef, useState } from "react";

type Word = {
  t: string;
  top: number;
  left: number;
  size: number;
  rot: number;
  op: number;
  strike?: boolean;
};

const UNSAID: Word[] = [
  { t: "我没事", top: 50, left: 50, size: 46, rot: -3, op: 0.6, strike: true },
  { t: "好累", top: 30, left: 30, size: 40, rot: -7, op: 0.5 },
  { t: "撑不住了", top: 68, left: 60, size: 36, rot: 4, op: 0.5 },
  { t: "算了", top: 22, left: 66, size: 34, rot: 6, op: 0.45 },
  { t: "我挺好的", top: 28, left: 50, size: 26, rot: 3, op: 0.36, strike: true },
  { t: "没人懂", top: 60, left: 27, size: 30, rot: -5, op: 0.42 },
  { t: "习惯了", top: 40, left: 72, size: 28, rot: -4, op: 0.4 },
  { t: "忍一忍", top: 46, left: 39, size: 24, rot: 6, op: 0.34 },
  { t: "不想说话", top: 78, left: 38, size: 26, rot: 3, op: 0.38 },
  { t: "我可以的", top: 52, left: 80, size: 26, rot: 5, op: 0.34, strike: true },
  { t: "怕麻烦别人", top: 14, left: 44, size: 24, rot: 2, op: 0.32 },
  { t: "说了也没用", top: 86, left: 63, size: 24, rot: -3, op: 0.3 },
  { t: "又失眠了", top: 62, left: 47, size: 22, rot: -3, op: 0.32 },
  { t: "都怪我", top: 18, left: 82, size: 22, rot: -2, op: 0.3 },
  { t: "没关系", top: 35, left: 15, size: 22, rot: -6, op: 0.3 },
  { t: "假装没事", top: 90, left: 23, size: 22, rot: -4, op: 0.28 },
  { t: "是我太敏感吗", top: 56, left: 64, size: 20, rot: 2, op: 0.26 },
  { t: "谁都靠不住", top: 12, left: 62, size: 20, rot: -4, op: 0.26 },
  { t: "笑一笑就好", top: 72, left: 84, size: 20, rot: 4, op: 0.26 },
  { t: "别想了", top: 8, left: 25, size: 20, rot: 5, op: 0.26 },
  { t: "没胃口", top: 84, left: 48, size: 18, rot: -5, op: 0.24 },
  { t: "没意思", top: 76, left: 14, size: 20, rot: 5, op: 0.24 },
];

export function WordWall() {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  const [reduce, setReduce] = useState(false);

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setReduce(true);
      setShown(true);
      return;
    }
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className="absolute inset-0">
      {UNSAID.map((w, i) => (
        <span
          key={i}
          className="font-hand pointer-events-none absolute whitespace-nowrap select-none"
          style={{
            top: `${w.top}%`,
            left: `${w.left}%`,
            transform: `translate(-50%, -50%) rotate(${w.rot}deg)`,
            fontSize: `${w.size}px`,
            color: `rgba(80,68,55,${w.op})`,
            textDecoration: w.strike ? "line-through" : undefined,
            textDecorationThickness: w.strike ? "2px" : undefined,
            opacity: reduce || shown ? 1 : 0,
            transition: reduce ? undefined : `opacity 600ms ease-out ${i * 45}ms`,
          }}
        >
          {w.t}
        </span>
      ))}
    </div>
  );
}
