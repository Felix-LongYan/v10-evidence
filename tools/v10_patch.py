#!/usr/bin/env python3
"""
v10_patch.py —— 给 V10 打一个"约束强制 + 合法性日志"的补丁。

原则：
  * **绝不修改原文件**。原文件是你"发现问题"的证据，必须保持原样。
  * 生成 `caocao_deepseek_v11.py`，与原文件并排放置。
  * 每一处替换都断言"恰好找到 1 处"，找不到就报错退出——绝不静默改坏。

修掉三件事：
  1. ±12 边界：原先只写在提示词里，代码不检查  → 改为代码强制
  2. "false" 误触发：`if not result.get(...)` 让字符串 "false" 为真 → 改为 `is not True`
  3. 半更新无回滚：逐字段写入，中途报错留下半个状态 → 改为"先全部算完，再一次性写入"

新增一件事：
  4. 合法性日志：每次状态更新都记录是否越界，并写入 CSV

用法：
    python3 v10_patch.py                      # 生成 v11 并打印改动摘要
    python3 v10_patch.py --diff               # 额外打印逐行 diff
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path

SRC = Path.home() / "Desktop" / "面试的项目" / "caocao_deepseek.py"
DST = Path.home() / "Desktop" / "面试的项目" / "caocao_deepseek_v11.py"

# ---------------------------------------------------------------- 新的辅助代码
HELPERS = '''

# ======================================================================
# 以下为 v11 补丁新增：约束强制 + 合法性日志
# 原版的问题：约束写在提示词里，代码不检查。
# ======================================================================

DELTA_BOUND = 12          # v11：提示词里写的 ±12，现在由代码强制
_LEGALITY_ROWS: list[dict] = []


def record_legality(field: str, raw, applied: int, before: int) -> None:
    """记录一次状态更新是否越界。raw 是模型给的原始值。"""
    problem = []
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        problem.append("not_a_number")
    else:
        if abs(raw) > DELTA_BOUND:
            problem.append(f"delta_exceeds_±{DELTA_BOUND}")
    after_unclamped = before + applied
    if not (0 <= after_unclamped <= 100):
        problem.append("result_out_of_range")
    _LEGALITY_ROWS.append({
        "field": field,
        "raw_delta": raw,
        "applied_delta": applied,
        "before": before,
        "after": clamp_score(after_unclamped),
        "violation": "|".join(problem) or "",
    })


def safe_delta(raw) -> int:
    """把模型给的 delta 变成合法整数：非数字→0，超界→截到 ±DELTA_BOUND。"""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 0
    return int(max(-DELTA_BOUND, min(DELTA_BOUND, raw)))


def dump_legality(path: str = "legality.csv") -> None:
    """把合法性日志写进 CSV，并打印一行统计。

    v11 行为：**追加**写入（文件不存在时才写表头），
    这样连续跑多次不会互相覆盖，可以累积统计。
    """
    if not _LEGALITY_ROWS:
        return
    import csv as _csv
    import os as _os
    bad = [r for r in _LEGALITY_ROWS if r["violation"]]
    fresh = not _os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(_LEGALITY_ROWS[0].keys()))
        if fresh:
            w.writeheader()
        w.writerows(_LEGALITY_ROWS)
    print(f"\\n（v11 合法性日志：本次 {len(_LEGALITY_ROWS)} 次更新，"
          f"其中 {len(bad)} 次违反声明约束 → {path}）")
'''

# ---------------------------------------------------------------- 替换 1：apply 函数
OLD_APPLY_START = '''def apply_jingzhou_eval_result(game_state: dict, eval_result: dict) -> None:
    if eval_result.get("relevance") == "none":
        print("（荆州线：本轮话题与刘表/荆州关联较弱，数值基本不变。）\\n")
        return
    jz = game_state["jingzhou"]'''

NEW_APPLY_START = '''def apply_jingzhou_eval_result(game_state: dict, eval_result: dict) -> None:
    if eval_result.get("relevance") == "none":
        print("（荆州线：本轮话题与刘表/荆州关联较弱，数值基本不变。）\\n")
        return
    # ---- v11 修改：先全部算完并校验，确认无误后再一次性写入（原子更新）----
    jz = game_state["jingzhou"]
    _FIELDS = ("liu_biao_trust", "jingzhou_interest", "tuogu_acceptance",
               "qi_cong_care", "ren_defer_tendency")
    _new: dict[str, int] = {}
    for _f in _FIELDS:
        _raw = eval_result.get(f"delta_{_f}", 0)
        _applied = safe_delta(_raw)
        record_legality(_f, _raw, _applied, jz[_f])
        _new[_f] = clamp_score(jz[_f] + _applied)
    for _f in _FIELDS:
        jz[_f] = _new[_f]'''

# 把原来的 5 段 clamp_score 赋值整体删掉（它们已被上面的循环取代）
OLD_APPLY_BODY = '''    jz["liu_biao_trust"] = clamp_score(
        jz["liu_biao_trust"] + eval_result.get("delta_liu_biao_trust", 0)
    )
    jz["jingzhou_interest"] = clamp_score(
        jz["jingzhou_interest"] + eval_result.get("delta_jingzhou_interest", 0)
    )
    jz["tuogu_acceptance"] = clamp_score(
        jz["tuogu_acceptance"] + eval_result.get("delta_tuogu_acceptance", 0)
    )
    jz["qi_cong_care"] = clamp_score(
        jz["qi_cong_care"] + eval_result.get("delta_qi_cong_care", 0)
    )
    jz["ren_defer_tendency"] = clamp_score(
        jz["ren_defer_tendency"] + eval_result.get("delta_ren_defer_tendency", 0)
    )'''

NEW_APPLY_BODY = '''    # （v11：上面已用循环原子写入，此处不再逐字段赋值）'''

OLD_MAIN = '''if __name__ == "__main__":
    # 解析命令行（如 python caocao_deepseek.py --demo）
    args = parse_cli_args()
    if args.demo:
        # 演示模式：跑完自动流程后退出
        run_demo_mode()
    else:
        # 正常交互模式
        run_game_loop()'''

NEW_MAIN = '''if __name__ == "__main__":
    # 解析命令行（如 python caocao_deepseek.py --demo）
    args = parse_cli_args()
    try:
        if args.demo:
            # 演示模式：跑完自动流程后退出
            run_demo_mode()
        else:
            # 正常交互模式
            run_game_loop()
    finally:
        # ---- v11 新增：退出前把合法性日志落盘 ----
        dump_legality()'''

# ---------------------------------------------------------------- 替换 2：布尔判断
OLD_TRIGGER = '''    if not eval_result.get("tuogu_event_trigger"):
        return'''
NEW_TRIGGER = '''    # ---- v11 修改：严格判断 True。原版 `if not ...` 会让字符串 "false" 误触发 ----
    if eval_result.get("tuogu_event_trigger") is not True:
        return'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", action="store_true", help="打印逐行 diff")
    ap.add_argument("--out", type=Path, default=DST, help=f"输出路径（默认 {DST}）")
    args = ap.parse_args()

    if not SRC.exists():
        print(f"找不到原文件：{SRC}")
        return 2
    original = SRC.read_text(encoding="utf-8")
    text = original

    def replace_once(old: str, new: str, label: str) -> None:
        nonlocal text
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"❌ 锚点「{label}」找到 {n} 处（应为 1 处）。已中止，未写入任何文件。")
        text = text.replace(old, new, 1)
        print(f"  ✓ {label}")

    print("正在打补丁：")
    replace_once(OLD_APPLY_START, NEW_APPLY_START, "1/5 状态更新改为：代码强制 ±12 + 原子写入 + 记录日志")
    replace_once(OLD_APPLY_BODY, NEW_APPLY_BODY, "2/5 删除原来的逐字段赋值（已被循环取代）")
    replace_once(OLD_TRIGGER, NEW_TRIGGER, "3/5 事件触发改为严格判断 True")
    replace_once(OLD_MAIN, NEW_MAIN, "4/5 退出前把合法性日志写入 legality.csv")

    # 4/4 在 clamp_score 定义之后插入辅助函数
    anchor = "def clamp_score(value: int) -> int:"
    idx = text.find(anchor)
    if idx < 0:
        raise SystemExit("❌ 找不到 clamp_score 定义，已中止。")
    end = text.find("\n\n\n", idx)
    if end < 0:
        raise SystemExit("❌ 找不到 clamp_score 之后的分界，已中止。")
    text = text[:end] + HELPERS + text[end:]
    print("  ✓ 5/5 插入合法性日志与 safe_delta 辅助函数")

    args.out.write_text(text, encoding="utf-8")
    print(f"\n✅ 已生成 {args.out}")
    print(f"   原文件未改动：{SRC}")

    if args.diff:
        print("\n" + "=" * 68)
        for line in difflib.unified_diff(
            original.splitlines(), text.splitlines(),
            fromfile="caocao_deepseek.py", tofile="caocao_deepseek_v11.py", lineterm="",
        ):
            print(line)

    print("\n下一步：")
    print(f"  1) 语法检查： python3 -c \"import ast;ast.parse(open('{args.out.name}',encoding='utf-8').read())\"")
    print(f"  2) 重跑演示： cd ~/Desktop/面试的项目 && python3 {args.out.name} --demo")
    print(f"  3) 验证约束： python3 ~/Documents/deepseek-harness/default-workspace/constraint_demo.py --module caocao_deepseek_v11")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
