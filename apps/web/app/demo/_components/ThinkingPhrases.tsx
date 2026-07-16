"use client";

/**
 * 于你等待时的轮播短句，替代冷冰冰的省略号。
 * 每 ~1.6s 切一句，淡入淡出，不重复同一句。
 */

import { useEffect, useRef, useState } from "react";

const PHRASES = [
  "嗯…",
  "我在听。",
  "让我想一下。",
  "嗯，慢慢说。",
  "我在想怎么说。",
] as const;

const INTERVAL_MS = 1600;

interface Props {
  /** 转写阶段用更短的文案 */
  variant?: "transcribing" | "thinking";
}

export function ThinkingPhrases({ variant = "thinking" }: Props) {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);
  const prevIndexRef = useRef(-1);

  useEffect(() => {
    if (variant === "transcribing") return;

    const timer = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIndex((i) => {
          let next = (i + 1) % PHRASES.length;
          if (next === prevIndexRef.current) {
            next = (next + 1) % PHRASES.length;
          }
          prevIndexRef.current = next;
          return next;
        });
        setVisible(true);
      }, 280);
    }, INTERVAL_MS);

    return () => clearInterval(timer);
  }, [variant]);

  const text = variant === "transcribing" ? "嗯…" : PHRASES[index];

  return (
    <span
      className="inline-block text-stone-400 transition-opacity duration-300"
      style={{ opacity: visible ? 1 : 0 }}
    >
      {text}
    </span>
  );
}
