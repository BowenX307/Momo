"use client";

/**
 * 滚动进入视口时淡入上浮。IntersectionObserver,无第三方依赖。
 * 尊重 prefers-reduced-motion(直接静态显示)。
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
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
      { threshold: 0.25 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={className}
      style={
        reduce
          ? undefined
          : {
              opacity: shown ? 1 : 0,
              transform: shown ? "translateY(0)" : "translateY(22px)",
              transition: `opacity 800ms ease-out ${delay}ms, transform 800ms cubic-bezier(0.16,1,0.3,1) ${delay}ms`,
              willChange: "opacity, transform",
            }
      }
    >
      {children}
    </div>
  );
}
