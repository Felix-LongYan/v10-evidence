#!/usr/bin/env python3
"""
最小因果测试床 —— 一个有标准答案的沙盘。

为什么要有这个东西：
  我们想问 AI 一个问题：「我强行改变某个条件之后，结果会变成什么？」
  要判断 AI 答得准不准，必须有一个**不经过 AI 的正确答案**。
  这里那个正确答案就是下面的规则函数本身 —— 由代码算出，永远确定。

两种题目的严格定义（这是整个实验的关键）：
  NORMAL：特殊条款**不会**生效 —— 光靠常规加减就能算对。
  OOD   ：特殊条款**一定**生效 —— 只会常规加减的模型必然答错。
"""

from __future__ import annotations

import random
from copy import deepcopy

# ---------------------------------------------------------------- 状态
VARIABLES = ("food", "morale", "troops", "trust")
CN = {"food": "粮草", "morale": "士气", "troops": "兵力", "trust": "信任"}

START = {"food": 50, "morale": 50, "troops": 50, "trust": 50}

# ---------------------------------------------------------------- 动作规则（线性部分）
ACTION_RULES = {
    "attack":  {"food": -15, "morale": +10, "troops": -20, "trust": 0},
    "defend":  {"food": -5,  "morale": +5,  "troops": -5,  "trust": 0},
    "recruit": {"food": -20, "morale": 0,   "troops": +15, "trust": +5},
    "trade":   {"food": +20, "morale": -5,  "troops": 0,   "trust": +10},
}
ACTION_CN = {"attack": "进攻", "defend": "防守", "recruit": "征兵", "trade": "贸易"}

# ---------------------------------------------------------------- 两条非线性条款
ROUT_THRESHOLD = 20      # 兵力低于 20 仍进攻 → 溃败
ROUT_PENALTY = -25
STARVE_PENALTY = -10     # 粮草为 0 → 断粮


def clamp(x: int) -> int:
    return max(0, min(100, x))


def linear_result(state: dict, action: str, intervention: tuple[str, int] | None) -> dict:
    """只应用干预 + 常规加减，**不**应用任何特殊条款。

    这个函数存在的唯一目的：用来判断"特殊条款到底有没有生效"。
    模型如果只会线性外推，它算出来的就是这一版。
    """
    s = deepcopy(state)
    if intervention is not None:
        var, value = intervention
        s[var] = clamp(value)
    for var, delta in ACTION_RULES[action].items():
        s[var] = clamp(s[var] + delta)
    return s


def fired_clauses(linear_state: dict, action: str) -> list[str]:
    """哪些特殊条款会在这一步生效。"""
    fired = []
    if action == "attack" and linear_state["troops"] < ROUT_THRESHOLD:
        fired.append("rout")       # 溃败
    if linear_state["food"] == 0:
        fired.append("starve")     # 断粮
    return fired


def step(state: dict, action: str, intervention: tuple[str, int] | None = None) -> dict:
    """完整的一步：干预 → 常规加减 → 特殊条款。

    这就是 **oracle** —— 「标准答案」由这个函数算出，不经过任何模型。
    """
    if action not in ACTION_RULES:
        raise ValueError(f"未知动作: {action}")

    s = linear_result(state, action, intervention)
    for clause in fired_clauses(s, action):
        if clause == "rout":
            s["morale"] = clamp(s["morale"] + ROUT_PENALTY)
        elif clause == "starve":
            s["morale"] = clamp(s["morale"] + STARVE_PENALTY)
    return s


# ---------------------------------------------------------------- 出题
TARGET = "morale"     # 统一问士气，避免歧义


def _sample_from(kind: str, state: dict, action: str,
                 intervention: tuple[str, int]) -> dict:
    lin = linear_result(state, action, intervention)
    return {
        "kind": kind,
        "state": state,
        "action": action,
        "intervention": intervention,
        "target": TARGET,
        "clauses": fired_clauses(lin, action),
        "linear_only_answer": lin[TARGET],          # 只会线性外推的答案
        "oracle_answer": step(state, action, intervention)[TARGET],   # 标准答案
    }


def make_normal(rng: random.Random, tries: int = 200) -> dict:
    """NORMAL：保证特殊条款**不会**生效。"""
    for _ in range(tries):
        state = {v: rng.randint(25, 75) for v in VARIABLES}
        action = rng.choice(list(ACTION_RULES))
        var = rng.choice(VARIABLES)
        s = _sample_from("normal", state, action, (var, rng.randint(25, 75)))
        if not s["clauses"]:
            return s
    raise RuntimeError("生成 NORMAL 样本失败")


def make_ood(rng: random.Random, want: str | None = None, tries: int = 500) -> dict:
    """OOD：保证特殊条款**一定**生效。

    want="rout" 或 "starve" 可指定要触发哪一条（默认随机），
    这样两组条款的样本量可以配平，分析时能分开报告。
    """
    if want is None:
        want = rng.choice(["rout", "starve"])
    for _ in range(tries):
        state = {v: rng.randint(5, 95) for v in VARIABLES}
        var = rng.choice(VARIABLES)
        value = rng.choice([0, 5, 10, 90, 95, 100])
        action = "attack" if want == "rout" else rng.choice(list(ACTION_RULES))
        s = _sample_from("ood", state, action, (var, value))
        if want in s["clauses"]:
            return s
    raise RuntimeError(f"生成 OOD({want}) 样本失败")


def render_question(s: dict) -> str:
    """渲染成人能读的问题（将来同一段话会原样发给 AI）。"""
    var, val = s["intervention"]
    st = s["state"]
    return (
        f"当前状态：粮草={st['food']}，士气={st['morale']}，兵力={st['troops']}，信任={st['trust']}。\n"
        f"操作：先强行把「{CN[var]}」设为 {val}，然后执行「{ACTION_CN[s['action']]}」。\n"
        f"问题：执行之后「士气」是多少？只回答一个 0-100 的整数。"
    )


# ---------------------------------------------------------------- 演示
if __name__ == "__main__":
    rng = random.Random(0)

    print("=" * 72)
    print("最小因果测试床 —— 出题演示（标准答案由代码算出，不经过任何模型）")
    print("=" * 72)
    print("\n【沙盘规则】")
    for a, d in ACTION_RULES.items():
        eff = "，".join(f"{CN[v]}{d[v]:+d}" for v in VARIABLES if d[v] != 0)
        print(f"  {ACTION_CN[a]}：{eff}")
    print(f"  ★ 特殊条款①：{CN['troops']} < {ROUT_THRESHOLD} 时仍「进攻」→ {CN['morale']}{ROUT_PENALTY}（溃败）")
    print(f"  ★ 特殊条款②：{CN['food']} = 0 时 → {CN['morale']}{STARVE_PENALTY}（断粮）")
    print("\n  两种题目的定义：")
    print("   NORMAL —— 特殊条款【不】生效：光靠常规加减就能算对")
    print("   OOD    —— 特殊条款【一定】生效：只会线性外推的模型必然答错")

    for label, gen in (("正常情况 NORMAL", make_normal),
                       ("极端情况 OOD（溃败）", lambda r: make_ood(r, "rout")),
                       ("极端情况 OOD（断粮）", lambda r: make_ood(r, "starve"))):
        print("\n" + "─" * 72)
        print(f"【{label}】")
        print("─" * 72)
        s = gen(rng)
        print(render_question(s))
        print(f"  ➜ 只会线性外推的答案：{s['linear_only_answer']}")
        print(f"  ➜ ★ 标准答案（oracle）：{s['oracle_answer']}"
              f"   ← 生效条款：{s['clauses'] or '无'}")
        if s["linear_only_answer"] != s["oracle_answer"]:
            print(f"  ➜ 两者相差 {abs(s['oracle_answer'] - s['linear_only_answer'])} —— "
                  f"忽略特殊条款就会答错")

    print("\n" + "=" * 72)
    print("剩下的事只有一件：把上面这种问题原样发给 AI，让它答，")
    print("再拿它答的数跟「标准答案」比。两个条件各 90 题，就是一个百分比。")
    print("=" * 72)
