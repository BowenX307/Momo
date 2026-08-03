#!/usr/bin/env bash
# 把线上实际生效的人格 prompt 拉一份快照到 docs/prompt-snapshots/。
#
# 为什么需要这个:线上真正生效的 prompt 在服务器的 runtime_overrides.json 里,产品在
# /internal 后台随时改写。那个文件不适合直接纳管(会天天冲突),但它是产品的核心资产——
# 没有历史就无法回答"上周优优为什么那样说话""这次改动前是什么样"。
#
# 用法:  ./scripts/snapshot_prompts.sh
# 建议:  产品在后台改完 prompt 后跑一次;发版前也跑一次。
#
# 输出是**只读参考**,不会被任何代码加载。改 prompt 请走后台,不要改快照文件。

set -euo pipefail

SERVER="${YEWNE_SERVER:-root@101.133.150.57}"
REMOTE="/root/momo/services/api/app/llm/runtime_overrides.json"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docs/prompt-snapshots"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$OUT_DIR"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

echo "从 $SERVER 拉取线上 prompt..."
ssh "$SERVER" "cat $REMOTE" > "$TMP"

# 拆成人类可读的 markdown:整段 JSON 塞进 git 历史 diff 起来没法看。
python3 - "$OUT_DIR" "$STAMP" "$TMP" <<'PY'
import json, sys, pathlib
out_dir, stamp, src = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
data = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))

lines = [
    f"# 线上 prompt 快照 · {stamp}",
    "",
    f"来源:服务器 `runtime_overrides.json`,后台最后更新于 `{data.get('updated_at', '未知')}`。",
    "",
    "⚠️ 这是**只读快照**,改 prompt 请走 /internal 后台,改这个文件不会有任何效果。",
    "",
    "## 采样参数",
    "",
    "| 参数 | 值 |",
    "| --- | --- |",
]
for k, v in (data.get("params") or {}).items():
    lines.append(f"| `{k}` | `{v}` |")

for name, text in (data.get("personas") or {}).items():
    lines += ["", f"## 人格:{name}({len(text)} 字)", "", "```text", text.rstrip(), "```"]

(out_dir / f"{stamp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
(out_dir / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"已写入 {out_dir}/{stamp}.md")
print(f"       {out_dir}/latest.md  (总是指向最新一次,方便直接看 diff)")
PY

echo
echo "下一步:git add docs/prompt-snapshots && git commit"
