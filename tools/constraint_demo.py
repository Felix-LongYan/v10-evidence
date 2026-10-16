#!/usr/bin/env python3
"""
constraint_demo.py —— 零 API 调用，验证 V10 / v11 的约束强制力。

和 v1 版本的区别：**结论是从观察到的行为算出来的**，不是写死的。
所以同一个脚本可以测原版和打过补丁的版本，直接对照。

用法：
    python3 constraint_demo.py                                    # 测原版 V10
    python3 constraint_demo.py --module caocao_deepseek_v11 --path testbed/patched
    python3 constraint_demo.py --both                              # 两个版本一起测并对照
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

DEFAULT_PATH = Path.home() / "Desktop" / "面试的项目"
BAR = "=" * 68


def load(module_name: str, path: Path):
    """从指定目录导入模块。"""
    sys.path.insert(0, str(path))
    for k in list(sys.modules):
        if k == module_name:
            del sys.modules[k]
    mod = importlib.import_module(module_name)
    sys.path.pop(0)
    return mod


# ---------------------------------------------------------------- 三个检验
def check_delta(mod) -> dict:
    """提示词说 ±12；代码是否强制？"""
    state = mod.create_initial_game_state()
    before = state["jingzhou"]["liu_biao_trust"]
    try:
        mod.apply_jingzhou_eval_result(state, {
            "relevance": "high",
            "delta_liu_biao_trust": 50, "delta_jingzhou_interest": -40,
            "delta_tuogu_acceptance": 0, "delta_qi_cong_care": 0,
            "delta_ren_defer_tendency": 0,
            "causal_reason": "检验：故意超出 ±12",
        })
    except Exception as exc:  # noqa: BLE001
        return {"err": f"{type(exc).__name__}: {exc}"}
    applied = state["jingzhou"]["liu_biao_trust"] - before
    return {"before": before, "applied": applied,
            "enforced": applied != 50}


def check_trigger(mod) -> dict:
    """字符串 "false" 会不会误触发事件？"""
    state = mod.create_initial_game_state()
    try:
        mod.maybe_trigger_liubiao_tuogu_event(state, {"tuogu_event_trigger": "false"})
    except Exception as exc:  # noqa: BLE001
        return {"err": f"{type(exc).__name__}: {exc}"}
    fired = state["liubiao_npc"]["tuogu_offered"]
    return {"fired": fired, "enforced": not fired}


def check_atomic(mod) -> dict:
    """非法的 delta 会不会留下'半更新'的状态？

    两种合格行为：
      A) 抛异常，但一个字段都没改（回滚）
      B) 不抛异常，把非法值中和，五个字段一致更新
    不合格行为：抛异常了，却已经写进去一部分。
    """
    state = mod.create_initial_game_state()
    before = dict(state["jingzhou"])
    try:
        mod.apply_jingzhou_eval_result(state, {
            "relevance": "high",
            "delta_liu_biao_trust": 10, "delta_jingzhou_interest": 10,
            "delta_tuogu_acceptance": "十",          # 类型错误
            "delta_qi_cong_care": 0, "delta_ren_defer_tendency": 0,
            "causal_reason": "检验：第三个字段类型错误",
        })
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    after = state["jingzhou"]
    changed = [k for k in before if before[k] != after[k]]
    partial = bool(raised and changed)             # 唯一不合格的情形
    return {"raised": raised, "changed": changed,
            "enforced": not partial,
            "mode": ("回滚" if raised and not changed
                     else "中和非法值" if not raised
                     else "半更新残留")}


def check_logging(mod) -> dict:
    """是否把'模型试图越界'这件事记录下来了？（v11 新增的仪器能力）"""
    rows = getattr(mod, "_LEGALITY_ROWS", None)
    if rows is None:
        return {"enforced": False, "mode": "没有合法性日志"}
    state = mod.create_initial_game_state()
    mod.apply_jingzhou_eval_result(state, {
        "relevance": "high",
        "delta_liu_biao_trust": 50,               # 越界，应被记录
        "delta_jingzhou_interest": 0, "delta_tuogu_acceptance": 0,
        "delta_qi_cong_care": 0, "delta_ren_defer_tendency": 0,
        "causal_reason": "检验：审计日志是否记录越界",
    })
    bad = [r for r in rows if r.get("violation")]
    return {"enforced": bool(bad), "mode": f"记录 {len(rows)} 条，其中越界 {len(bad)} 条",
            "sample": bad[0] if bad else None}


# ---------------------------------------------------------------- 报告
def report(label: str, mod) -> dict:
    print()
    print(BAR)
    print(f"【{label}】")
    print(BAR)

    d = check_delta(mod)
    print("\n检验 1：提示词的 ±12 是否被代码强制？")
    if "err" in d:
        print(f"  异常：{d['err']}")
    else:
        print(f"  传入 delta = +50，实际生效 = {d['applied']:+d}（初始值 {d['before']}）")
        print(f"  ➜ {'✅ 已强制（被截到合法范围）' if d['enforced'] else '❌ 未强制（原样接受）'}")

    t = check_trigger(mod)
    print("\n检验 2：字符串 \"false\" 会不会误触发事件？")
    if "err" in t:
        print(f"  异常：{t['err']}")
    else:
        print(f"  事件标记 = {t['fired']}")
        print(f"  ➜ {'✅ 已强制（正确拒绝 \"false\"）' if t['enforced'] else '❌ 未强制（\"false\" 被当真）'}")

    a = check_atomic(mod)
    print("\n检验 3：非法 delta 会不会留下'半更新'状态？")
    if "err" in a:
        print(f"  异常：{a['err']}")
    else:
        print(f"  抛出异常：{a['raised']}　被改动的字段：{a['changed'] or '无'}")
        print(f"  处理方式：{a.get('mode', '—')}")
        print(f"  ➜ {'✅ 合格（无半更新残留）' if a['enforced'] else '❌ 不合格（写到一半就停了）'}")

    g = check_logging(mod)
    print("\n检验 4：会不会把'模型试图越界'记录下来？（仪器能力）")
    print(f"  {g.get('mode', '—')}")
    if g.get("sample"):
        print(f"  记录样例：{g['sample']}")
    print(f"  ➜ {'✅ 会记录' if g['enforced'] else '❌ 不记录（只吞掉，不留痕）'}")

    return {"delta": d.get("enforced"), "trigger": t.get("enforced"),
            "atomic": a.get("enforced"), "logging": g.get("enforced")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", default="caocao_deepseek")
    ap.add_argument("--path", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--both", action="store_true", help="同时测原版和 v11 并对照")
    args = ap.parse_args()

    if args.both:
        results = {}
        for label, mod_name, path in (
            ("原版 V10（caocao_deepseek.py）", "caocao_deepseek", args.path),
            ("补丁版 v11（caocao_deepseek_v11.py）", "caocao_deepseek_v11", args.path),
        ):
            if not (path / f"{mod_name}.py").exists():
                print(f"\n跳过 {label}：找不到 {path / (mod_name + '.py')}")
                continue
            results[label] = report(label, load(mod_name, path))

        print()
        print(BAR)
        print("【对照结论】")
        print(BAR)
        print(f"{'检验项':<28}{'原版 V10':<14}{'补丁版 v11':<14}")
        names = {"delta": "±12 是否被强制", "trigger": "\"false\" 是否被拒",
                 "atomic": "无半更新残留", "logging": "是否记录越界"}
        keys = list(results)
        if len(keys) == 2:
            a, b = results[keys[0]], results[keys[1]]
            for k, cn in names.items():
                fmt = lambda v: ("✅ 是" if v else "❌ 否") if v is not None else "—"
                print(f"{cn:<26}{fmt(a.get(k)):<16}{fmt(b.get(k)):<16}")
        print()
        return 0

    enforced = report(args.module, load(args.module, args.path))
    n = sum(1 for v in enforced.values() if v)
    print(f"\n{BAR}\n三项约束中已强制 {n}/3\n{BAR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
