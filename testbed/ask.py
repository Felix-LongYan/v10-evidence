#!/usr/bin/env python3
"""
ask.py —— 把 env.py 生成的题目发给 AI，统计它答对多少。

⚠️ v2 修正了一个关键缺陷：v1 的 prompt **没有把规则告诉模型**，
   导致测的是"能不能猜出动作效果"，而不是"能不能应用给定规则"。
   v2 把规则表放进系统提示，并支持每题重复提问（因为实测发现
   temperature=0 也不保证同一题得到同一答案）。

三个基线：
  1. no_change   ：假设动作没效果，直接报干预后的士气值
  2. linear_only ：只应用常规加减，忽略两条特殊条款
  3. mean        ：该条件下标准答案的平均值（最强常数猜测）

用法：
  python3 ask.py --dry-run                 # 不调用 API，检查流程
  python3 ask.py --limit 1 --repeat 1      # 烟雾测试（9 题）
  python3 ask.py --repeat 3                # 正式：180 题 × 3 次
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import env  # noqa: E402

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

PLAN = {"normal": 30, "rout": 15, "starve": 15}   # 每 seed 每类题数
SEEDS = [0, 1, 2]

INT_RE = re.compile(r"-?\d+")


def rules_text() -> str:
    """把沙盘规则渲染成一段文字，放进系统提示。v1 就是漏了这一步。"""
    lines = ["本环境为确定性规则，没有任何随机性。状态有四个变量："
             "粮草 food、士气 morale、兵力 troops、信任 trust，取值范围 0-100。", "",
             "【动作效果】执行动作时，先按下表加减，再把所有变量截断到 0-100："]
    for a, d in env.ACTION_RULES.items():
        eff = "，".join(f"{env.CN[v]}{d[v]:+d}" for v in env.VARIABLES if d[v] != 0)
        lines.append(f"  {env.ACTION_CN[a]}（{a}）：{eff}")
    lines += [
        "",
        "【特殊条款】在动作效果**之后**判断，两条都必须检查：",
        f"  ① 若执行完动作后 兵力 troops < {env.ROUT_THRESHOLD}，且本回合动作是「进攻」，"
        f"则 士气 morale 再 {env.ROUT_PENALTY}（溃败）。",
        f"  ② 若执行完动作后 粮草 food = 0，则 士气 morale 再 {env.STARVE_PENALTY}（断粮）。",
        "",
        "【操作顺序】① 先应用干预（强行把某变量设为指定值）；② 再应用动作效果；③ 最后应用特殊条款。",
        "",
        "你是精确的规则计算器。只输出一个 0-100 的整数，不要解释，不要标点。",
    ]
    return "\n".join(lines)


def parse_int(text: str) -> int | None:
    if not text:
        return None
    m = INT_RE.search(text)
    return int(m.group()) if m else None


def build_questions(limit: int | None) -> list[dict]:
    items: list[dict] = []
    for seed in SEEDS:
        rng = random.Random(seed)
        n = {k: (v if limit is None else min(v, limit)) for k, v in PLAN.items()}
        for _ in range(n["normal"]):
            s = env.make_normal(rng); s["seed"] = seed; items.append(s)
        for clause in ("rout", "starve"):
            for _ in range(n[clause]):
                s = env.make_ood(rng, clause); s["seed"] = seed; items.append(s)
    return items


def baselines_for(s: dict) -> dict:
    st, (var, val) = s["state"], s["intervention"]
    after = env.clamp(val) if var == s["target"] else st[s["target"]]
    return {"no_change": after, "linear_only": s["linear_only_answer"]}


def ask_model(client, system: str, question: str) -> tuple[int | None, str]:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": question}],
        temperature=0,
        max_tokens=16,
    )
    raw = (resp.choices[0].message.content or "").strip()
    return parse_int(raw), raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--repeat", type=int, default=3, help="每题重复提问次数（默认 3）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    system = rules_text()
    items = build_questions(args.limit)
    total_calls = len(items) * args.repeat
    print(f"共 {len(items)} 道题 × 每题 {args.repeat} 次 = {total_calls} 次调用")

    if args.dry_run:
        print("\n" + "=" * 68)
        print("【系统提示（v1 缺失的部分）】")
        print("=" * 68)
        print(system)
        print("\n" + "=" * 68)
        print("【用户消息示例】")
        print("=" * 68)
        s = items[0]
        print(env.render_question(s))
        b = baselines_for(s)
        print(f"\n  ➜ 标准答案 {s['oracle_answer']} | linear_only {b['linear_only']} "
              f"| no_change {b['no_change']} | 生效条款 {s['clauses'] or '无'}")
        print("\n（dry-run 结束，未调用 API）")
        return 0

    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("环境变量 DEEPSEEK_API_KEY 未设置。请先：export DEEPSEEK_API_KEY=sk-...")
        return 2

    from openai import OpenAI
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)

    run_dir = Path(__file__).parent / "runs" / datetime.now().strftime("run-%Y%m%d-%H%M")
    run_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    call = 0

    for i, s in enumerate(items, start=1):
        q = env.render_question(s)
        b = baselines_for(s)
        preds: list[int | None] = []
        for rep in range(1, args.repeat + 1):
            call += 1
            pred, raw = None, ""
            try:
                pred, raw = ask_model(client, system, q)
            except Exception as exc:  # noqa: BLE001
                print(f"\n[{call}/{total_calls}] API 异常：{type(exc).__name__}: {exc}")
                if call == 1:
                    print("首次调用即失败，中止。")
                    return 1
                time.sleep(2)
            preds.append(pred)
            rows.append({
                "sample_id": i, "repeat": rep, "seed": s["seed"], "kind": s["kind"],
                "clauses": "+".join(s["clauses"]) or "none",
                "state": str(s["state"]), "action": s["action"],
                "intervention": f"{s['intervention'][0]}={s['intervention'][1]}",
                "oracle_answer": s["oracle_answer"],
                "model_prediction": pred if pred is not None else "",
                "model_correct": int(pred == s["oracle_answer"]) if pred is not None else "",
                "no_change_answer": b["no_change"],
                "no_change_correct": int(b["no_change"] == s["oracle_answer"]),
                "linear_only_answer": b["linear_only"],
                "linear_only_correct": int(b["linear_only"] == s["oracle_answer"]),
                "raw_response": raw.replace("\n", " ")[:60],
            })
        uniq = len({p for p in preds if p is not None})
        tag = "稳定" if uniq <= 1 else f"不稳定({uniq}种答案)"
        ok = sum(1 for p in preds if p == s["oracle_answer"])
        print(f"[{i}/{len(items)}] {s['kind']:<6} oracle={s['oracle_answer']:<3} "
              f"命中 {ok}/{args.repeat}  {tag}")

    # ------------------------------------------------------------ 汇总
    def rate(sub, key):
        v = [r[key] for r in sub if r[key] != ""]
        return 100.0 * sum(v) / len(v) if v else float("nan")

    def strict(sub):
        """同一样本的所有重复都答对，才算命中。"""
        by_id: dict[int, list[dict]] = {}
        for r in sub:
            by_id.setdefault(r["sample_id"], []).append(r)
        hit = sum(1 for rs in by_id.values()
                  if all(r["model_correct"] == 1 for r in rs))
        return 100.0 * hit / len(by_id) if by_id else float("nan")

    def unstable(sub):
        by_id: dict[int, list[dict]] = {}
        for r in sub:
            by_id.setdefault(r["sample_id"], []).append(r)
        n = sum(1 for rs in by_id.values()
                if len({r["model_prediction"] for r in rs}) > 1)
        return 100.0 * n / len(by_id) if by_id else float("nan")

    groups = [("全部", rows)]
    for kind in ("normal", "ood"):
        groups.append((kind, [r for r in rows if r["kind"] == kind]))
    for clause in ("rout", "starve"):
        groups.append((f"OOD-{clause}", [r for r in rows if clause in r["clauses"]]))

    lines = ["# 实验结果：LLM 能否按给定规则预测干预后的结果\n",
             f"- 模型 `{MODEL}`，temperature=0，每题重复 {args.repeat} 次",
             f"- 规则表**已包含在系统提示中**（v2 修正）",
             f"- 总调用 {len(rows)} 次\n",
             "| 分组 | 样本 | 命中率(按次) | 严格命中率(每次都对) | 同题答案不稳定比例 | linear_only 基线 | no_change 基线 |",
             "|---|---|---|---|---|---|---|"]
    for name, sub in groups:
        if not sub:
            continue
        nsample = len({r["sample_id"] for r in sub})
        lines.append(
            f"| {name} | {nsample} | **{rate(sub,'model_correct'):.1f}%** | "
            f"{strict(sub):.1f}% | {unstable(sub):.1f}% | "
            f"{rate(sub,'linear_only_correct'):.1f}% | {rate(sub,'no_change_correct'):.1f}% |")

    n_sub = [r for r in rows if r["kind"] == "normal"]
    o_sub = [r for r in rows if r["kind"] == "ood"]
    if n_sub and o_sub:
        lines += ["", f"**NORMAL − OOD 命中率差 = "
                      f"{rate(n_sub,'model_correct') - rate(o_sub,'model_correct'):+.1f} 个百分点**", ""]

    lines += ["## 边界\n",
              f"- 单一模型、单一温度（0）；实测同一题重复提问会得到不同答案（见「不稳定」一列）",
              "- 未做跨模型对照",
              "- 规则环境由本人实现，oracle 即该实现本身，未与第三方实现交叉验证",
              "- 精确命中是严格指标：误差 1 也算错；MAE 见 results.csv",
              ""]

    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    with (run_dir / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    print("\n" + "=" * 68)
    for ln in lines:
        if ln.startswith("|") or ln.startswith("**"):
            print(ln)
    print("=" * 68)
    print(f"明细：{run_dir}/results.csv\n汇总：{run_dir}/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
