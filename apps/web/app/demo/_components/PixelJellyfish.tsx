"use client";

/**
 * 像素水母（不是 chat box 的"陪伴体"）。
 *
 * 设计语义：
 * - 默认状态：缓慢呼吸 + 偶尔眨眼，"在场但不打扰"。
 * - thinking=true（等待后端时）：触手摆动加快、眼睛保持睁开，"在认真听"。
 * - degraded=true（上游降级到 mock 时）：颜色稍微偏冷灰，暗示"现在不是它最状态在线"。
 *
 * 实现：纯 SVG `<rect>` 像素方块，配 CSS keyframes，无需位图资源、可改色。
 */

import type { CSSProperties } from "react";

interface Props {
  thinking?: boolean;
  degraded?: boolean;
  size?: number;
}

const PIXEL = 8;
const COLS = 14;
const ROWS = 11;

// 像素图（以 14x11 网格手画）：
//   .: 透明  H: 头主色  S: 头亮色  E: 眼睛  T: 触手主色  t: 触手亮色
const ART: string[] = [
  "....HHHHHH....",
  "..HHSSSSSSHH..",
  ".HSSSSSSSSSSH.",
  "HSSSSSSSSSSSSH",
  "HSSEESSSSEESSH",
  "HSSEESSSSEESSH",
  "HSSSSSSSSSSSSH",
  "HHTTTHTTTHTTTH",
  ".T.T.T.T.T.T.T",
  "T...T...T...T.",
  ".T.....T.....T",
];

interface Palette {
  head: string;
  headLight: string;
  eye: string;
  tentacle: string;
  tentacleLight: string;
}

// 蜜桃橘色调，配米白底；不做发光，靠对比与体积感
const NORMAL_PALETTE: Palette = {
  head: "#e88c6a", // 蜜桃橘
  headLight: "#f5c4a0", // 蜜桃高光
  eye: "#3a2820", // 深暖棕
  tentacle: "#e88c6a",
  tentacleLight: "#f8d4b8",
};

// 降级时退到暖灰棕色调
const DEGRADED_PALETTE: Palette = {
  head: "#a89388",
  headLight: "#cdbfb4",
  eye: "#2d201a",
  tentacle: "#a89388",
  tentacleLight: "#e0d6cd",
};

function colorFor(ch: string, p: Palette): string | null {
  switch (ch) {
    case "H":
      return p.head;
    case "S":
      return p.headLight;
    case "E":
      return p.eye;
    case "T":
      return p.tentacle;
    case "t":
      return p.tentacleLight;
    default:
      return null;
  }
}

export function PixelJellyfish({ thinking = false, degraded = false, size = 168 }: Props) {
  const palette = degraded ? DEGRADED_PALETTE : NORMAL_PALETTE;
  const w = COLS * PIXEL;
  const h = ROWS * PIXEL;

  const wrapperStyle: CSSProperties = {
    width: size,
    height: (size * h) / w,
    animation: thinking
      ? "momo-breathe 2.4s ease-in-out infinite"
      : "momo-breathe 5s ease-in-out infinite",
    imageRendering: "pixelated",
  };

  return (
    <div style={wrapperStyle} aria-hidden="true">
      <style>{`
        @keyframes momo-breathe {
          0%, 100% { transform: translateY(0) scale(1); }
          50% { transform: translateY(-3px) scale(1.03); }
        }
        @keyframes momo-blink {
          0%, 92%, 100% { transform: scaleY(1); }
          94%, 98% { transform: scaleY(0.05); }
        }
        .momo-eye {
          transform-origin: center;
          transform-box: fill-box;
          animation: momo-blink 6.5s ease-in-out infinite;
        }
      `}</style>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width="100%"
        height="100%"
        shapeRendering="crispEdges"
      >
        {ART.flatMap((row, y) =>
          [...row].map((ch, x) => {
            const fill = colorFor(ch, palette);
            if (!fill) return null;
            const isEye = ch === "E";
            return (
              <rect
                key={`${x}-${y}`}
                x={x * PIXEL}
                y={y * PIXEL}
                // 略微 overscan 半个像素让相邻方块重叠覆盖，
                // 消除浏览器缩放 SVG 时相邻 <rect> 之间露出的亚像素缝。
                width={PIXEL + 0.5}
                height={PIXEL + 0.5}
                fill={fill}
                className={isEye ? "momo-eye" : undefined}
              />
            );
          }),
        )}
      </svg>
    </div>
  );
}
