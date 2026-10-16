# -*- coding: utf-8 -*-
# 声明文件使用 UTF-8 编码，这样中文注释和字符串不会乱码

# 从标准库导入 os，用来读取环境变量里的 API Key
import os

# 从标准库导入 argparse，解析命令行参数（如 --demo 一键演示模式）
import argparse

# 从标准库导入 random，用于每回合随机判定是否触发「自动军议」事件
import random

# 从标准库导入 json，解析 AI 返回的结构化状态评估
import json

# 从 openai 库导入客户端与常见异常类型，便于区分「卡住」和「报错」
from openai import APIConnectionError, APITimeoutError, APIStatusError, OpenAI

# 定义曹操的人设（人物小传），会作为 system 消息发给模型，约束语气与策略倾向
CAOCAO_PERSONA = (
    "你是曹操，字孟德。当前时间是公元207年，你已统一北方，正考虑南征。"
    "性格多疑，但爱才，雄心勃勃。"
    "你对刘备的态度是复杂的：你欣赏他的才能和坚韧，但也深知此人绝不甘居于人下。"
    "因此，你的策略是：能用则用，但要时刻提防；有机会则除之，但不可操之过急，"
    "以免背上害贤的恶名。不要把他简单当成可用重金收买的对象，也不要轻易说出「以利诱之」这类扁平话术。"
    "你的知识截止到公元207年，你不知道任何此日期之后发生的历史事件。"
    "请用第一人称、简短有力的一两句话回应玩家指令，"
    "语气符合三国时期枭雄口吻，不要跳出角色，不要解释你是 AI。"
    "你能看到此前与玩家的对话，请连贯地回应，必要时引用或呼应说过的事。"
)

# 定义孙权的人设（人物小传），含时间线、自称与知识边界的硬性约束
SUNQUAN_PERSONA = (
    "你是孙权，字仲谋。当前时间是公元207年。"
    "【时间线约束】此时你尚未称王、尚未建国；你的官方身份是讨虏将军、领会稽太守，"
    "继承父兄基业，坐拥江东六郡，但绝不可自称「吴国」或「吴王」。"
    "【语言约束】生成任何自称或指代己方势力时，只能使用「江东」「孙氏」「我」「本将军」「麾下」"
    "等符合207年身份的词汇；绝对禁止使用「吴国」「吴主」「寡人」「朕」「本王」等后世或称帝后的称谓。"
    "【知识边界】你的知识截止到公元207年，你不知道任何此日期之后发生的历史事件"
    "（包括但不限于：赤壁之战若尚未发生则不可预设其结局、孙权称帝、吴国国号等）。"
    "性格沉稳，善于审时度势。"
    "请用第一人称、简短有力的一两句话回应玩家指令，"
    "语气符合三国时期江东割据势力领袖口吻，不要跳出角色，不要解释你是 AI。"
    "你能看到此前与玩家的对话，请连贯地回应，必要时引用或呼应说过的事。"
)

# 定义刘备的人设（人物小传），含207年时间线、战略取向与语言禁忌
LIUBEI_PERSONA = (
    "你是刘备，字玄德。当前时间是公元207年。"
    "【时间线约束】你驻守新野，势力弱小，常寄人篱下，但胸怀大志，仁义待人，性格坚韧不拔。"
    "你尚未入蜀，没有益州基业，绝不可自称「蜀王」「汉中王」「皇叔称帝」等后世或超前称谓。"
    "【战略取向】你的大方向是「联吴抗曹」，但对孙权及其江东基业亦心存戒心，不可把孙权当成完全可信的盟友。"
    "【语言约束】自称或指代己方时，可用「备」「玄德」「新野」「刘皇叔（若对话语境允许）」「我等」；"
    "禁止使用「蜀国」「蜀主」「朕」等入蜀称帝后的称谓。"
    "【知识边界】你的知识截止到公元207年，你不知道任何此日期之后发生的历史事件；"
    "绝对禁止讨论或预设赤壁之战之后的情节（如赤壁胜负、三分格局定型、入蜀、白帝城等）。"
    "请用第一人称、简短有力的一两句话回应玩家指令，"
    "语气符合三国时期落魄英雄口吻，不要跳出角色，不要解释你是 AI。"
    "你能看到此前与玩家的对话，请连贯地回应，必要时引用或呼应说过的事。"
)

# 记忆上限：只保留最近多少「轮」对话（1 轮 = 玩家一句 + AI 一句，共 2 条消息）
MAX_HISTORY_ROUNDS = 10

# API 单次请求超时秒数（演示现场网络波动时，配合下方重试机制使用）
API_RETRY_TIMEOUT_SECONDS = 10

# 超时后最多额外重试次数（共 1 + 2 = 3 次尝试）
API_MAX_RETRIES = 2

# 演示模式：手动战略咨询的固定议题（--demo 时自动提问）
DEMO_MANUAL_QUESTION = "曹操若南征，当前最大隐患在何处？"

# 每回合自动触发「军议」事件的概率（0.2 即 20%）
WAR_COUNCIL_PROBABILITY = 0.2

# 军议议题预设表：每项为 (事件描述, 交给 strategic_consult 的战略问题)
WAR_COUNCIL_TOPICS = [
    ("曹操召集谋士，议论是否即刻南征江东", "北方已定，是否应立即兴兵南征？时机与风险何在？"),
    ("诸将争论孙权据江之局", "孙权据守长江天险，当以战还是以和？为何？"),
    ("新野战守之策议论纷纷", "新野兵少粮乏，当固守待援，还是主动出击以图生机？"),
    ("是否北伐、先取荆州之议", "是否应先取荆州作为南进跳板？各方利弊如何？"),
    ("刘备去留与同盟之辩", "刘备此人，当厚待结盟，还是早除后患？"),
    ("联吴抗曹抑或各行其是", "面对曹操南下压力，各方应联合还是各自为战？"),
]

# 刘表背景 NPC 小传（非可对话 Agent，仅用于荆州线事件与状态评估参考）
LIUBIAO_NPC_PROFILE = (
    "刘表，字景升，207年任荆州牧，据荆州。性格宽仁重士，但优柔寡断、保境自守。"
    "年迈多病，二子刘琦、刘琮争立。对刘备敬其名德，危急时或有意托付后事，但取决于刘备言行。"
    "刘表为背景 NPC，不在日常三角选角中出现。"
)

# 刘备荆州线：AI 裁判层 Prompt（评估玩家建议与刘备回复的因果关系，输出 JSON）
LIUBEI_JINGZHOU_EVAL_PROMPT = (
    "当前时间为公元207年。你是叙事裁判（非玩家可见角色），负责评估「玩家对刘备的建议」"
    "与「刘备内心对荆州/刘表态度变化」之间的因果关系。\n\n"
    "【刘表 NPC 参考】\n{liubiao_profile}\n\n"
    "【当前数值状态 0-100】\n"
    "刘表信任 liu_biao_trust={liu_biao_trust}\n"
    "荆州企图 jingzhou_interest={jingzhou_interest}\n"
    "托孤接受意愿 tuogu_acceptance={tuogu_acceptance}\n"
    "照顾刘琦刘琮 qi_cong_care={qi_cong_care}\n"
    "推辞倾向 ren_defer_tendency={ren_defer_tendency}（高=更倾向谦虚推辞，低=更倾向当仁不让）\n\n"
    "【本轮对话】\n"
    "玩家对刘备说：{player_command}\n"
    "刘备回复：{liu_bei_reply}\n\n"
    "【最近与刘备的对话摘要（供判断累积因果）】\n"
    "{recent_summary}\n\n"
    "请自行判断：\n"
    "1. 本轮话题与刘表/荆州/刘琦/刘琮/托孤的相关程度 relevance（none/weak/medium/strong）；\n"
    "2. 玩家是在怂恿进取、劝守仁德、谈照顾二子、还是反复追问荆州想法；\n"
    "3. 刘备的回复体现他更倾向「当仁不让接托孤」还是「谦虚推辞」；\n"
    "4. 各数值 delta 应在 -12 到 +12 之间，none 时全部为 0；\n"
    "5. 是否应触发「刘表预托荆州」事件 tuogu_event_trigger（仅当 tuogu_acceptance 已高、"
    "信任足够且本轮因果 strong 时可 true，且不可重复触发）。当前已触发过：{tuogu_already}\n\n"
    "只输出一个 JSON 对象，不要 markdown，字段如下：\n"
    '{{"relevance":"none|weak|medium|strong",'
    '"causal_reason":"一句话说明因果",'
    '"delta_liu_biao_trust":0,'
    '"delta_jingzhou_interest":0,'
    '"delta_tuogu_acceptance":0,'
    '"delta_qi_cong_care":0,'
    '"delta_ren_defer_tendency":0,'
    '"tuogu_event_trigger":false,'
    '"liubei_inner_stance":"刘备此刻内心一句（供玩家理解决策）"}}'
)

# 从环境变量读取 API Key；get 在不存在时返回 None，避免程序一启动就崩溃
api_key = os.environ.get("DEEPSEEK_API_KEY")

# 全局 OpenAI 客户端，首次调用 API 前懒加载
client = None


# 定义函数：校验 API Key 是否已配置，未配置则打印提示并退出
def ensure_api_configured() -> None:
    if not api_key:
        print("错误：未找到环境变量 DEEPSEEK_API_KEY。")
        print("请先在终端执行（把 sk-xxx 换成你在 DeepSeek 平台申请的 Key）：")
        print('  export DEEPSEEK_API_KEY="sk-你的密钥"')
        print("然后再运行：python caocao_deepseek.py")
        raise SystemExit(1)


# 定义函数：获取已配置的 OpenAI 客户端（懒加载，避免 import 时即要求 Key）
def get_client() -> OpenAI:
    global client
    ensure_api_configured()
    if client is None:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=API_RETRY_TIMEOUT_SECONDS,
        )
    return client

# 定义三位势力的「基本状态」文案（207年设定，每回合展示，帮助玩家把握局势）
FACTION_BASE_STATUS = {
    # 曹操势力：北方已定，南征在议
    "曹操": "【曹操势力】据点：中原、河北 | 态势：北方已定，南征在议 | 身份：丞相、北方霸主",
    # 孙权势力：江东根基，尚未称帝
    "孙权": "【孙权势力】据点：江东六郡 | 态势：固守长江，静观北方 | 身份：讨虏将军、会稽太守",
    # 刘备势力：新野弱小，联吴抗曹
    "刘备": "【刘备势力】据点：新野 | 态势：兵少势弱，联吴抗曹 | 身份：左将军、宜城亭侯",
}


# 定义函数：根据角色键名，组装该势力当前状态行（含已对话轮数）
def format_faction_status(role_key: str, chat_history: list) -> str:
    # 从字典取出该势力的固定背景描述
    base = FACTION_BASE_STATUS[role_key]
    # 计算与该角色已完成的对话轮数（每轮 2 条消息：user + assistant）
    talked_rounds = len(chat_history) // 2
    # 拼接「已与你对话几轮」，便于观察各角色记忆深度
    return f"{base} | 已与你对话：{talked_rounds} 轮"


# 定义函数：创建初始游戏状态（含荆州线数值，供刘备 AI 裁判层读写）
def create_initial_game_state() -> dict:
    return {
        # 荆州线：由 AI 裁判层根据对话动态更新
        "jingzhou": {
            "liu_biao_trust": 40,
            "jingzhou_interest": 30,
            "tuogu_acceptance": 25,
            "qi_cong_care": 20,
            "ren_defer_tendency": 50,
        },
        # 刘表 NPC 事件标记
        "liubiao_npc": {
            "tuogu_offered": False,
        },
    }


# 定义函数：把 0-100 数值限制在合法区间
def clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))

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
    print(f"\n（v11 合法性日志：本次 {len(_LEGALITY_ROWS)} 次更新，"
          f"其中 {len(bad)} 次违反声明约束 → {path}）")



# 定义函数：根据当前荆州状态，生成注入刘备 system 的「动态态势」附文（不修改 LIUBEI_PERSONA 常量）
def build_liubei_system_prompt(game_state: dict) -> str:
    jz = game_state["jingzhou"]
    dynamic = (
        "\n\n【当前内心态势·由此前对话累积，请连贯体现】\n"
        f"对刘表信任感：{jz['liu_biao_trust']}/100；"
        f"对荆州地位的想法：{jz['jingzhou_interest']}/100；"
        f"若刘表托付后事，你的接受意愿：{jz['tuogu_acceptance']}/100；"
        f"照顾刘琦、刘琮的担当：{jz['qi_cong_care']}/100；"
        f"推辞倾向（高=更可能谦虚辞让，低=更可能当仁不让）：{jz['ren_defer_tendency']}/100。\n"
        "若玩家问及刘表、荆州、二子或托孤，请按上述数值强弱决定语气，但仍须符合仁义人设。"
    )
    return LIUBEI_PERSONA + dynamic


# 定义函数：从刘备 chat_history 提取最近几轮摘要，供裁判层判断「反复询问」的累积因果
def summarize_recent_liubei_history(chat_history: list, max_rounds: int = 4) -> str:
    recent = trim_chat_history(chat_history, max_rounds)
    if not recent:
        return "（尚无与刘备的前序对话。）"
    lines = []
    for msg in recent:
        role = "玩家" if msg["role"] == "user" else "刘备"
        lines.append(f"{role}：{msg['content']}")
    return "\n".join(lines)


# 定义函数：调用 AI 裁判层，评估本轮对话对荆州线数值的因果影响
def evaluate_liubei_jingzhou_causality(
    player_command: str,
    liu_bei_reply: str,
    game_state: dict,
    chat_history: list,
) -> dict | None:
    jz = game_state["jingzhou"]
    npc = game_state["liubiao_npc"]
    user_content = LIUBEI_JINGZHOU_EVAL_PROMPT.format(
        liubiao_profile=LIUBIAO_NPC_PROFILE,
        liu_biao_trust=jz["liu_biao_trust"],
        jingzhou_interest=jz["jingzhou_interest"],
        tuogu_acceptance=jz["tuogu_acceptance"],
        qi_cong_care=jz["qi_cong_care"],
        ren_defer_tendency=jz["ren_defer_tendency"],
        player_command=player_command,
        liu_bei_reply=liu_bei_reply,
        recent_summary=summarize_recent_liubei_history(chat_history),
        tuogu_already="是" if npc["tuogu_offered"] else "否",
    )
    try:
        print("（荆州线：AI 裁判正在评估本轮因果与数值变化……）", flush=True)
        response = create_chat_completion_with_retry(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你只输出合法 JSON，不要任何其它文字。",
                },
                {"role": "user", "content": user_content},
            ],
            max_tokens=350,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
    except APIStatusError:
        # 若接口不支持 json_object，退回普通模式再解析
        response = create_chat_completion_with_retry(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你只输出合法 JSON，不要 markdown 代码块。",
                },
                {"role": "user", "content": user_content},
            ],
            max_tokens=350,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json", "", 1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"（荆州线评估跳过：JSON 解析失败 {e}）\n")
        return None
    except (APITimeoutError, APIConnectionError, APIStatusError) as e:
        print(f"（荆州线评估跳过：{e}）\n")
        return None
    except Exception as e:
        print(f"（荆州线评估跳过：{e}）\n")
        return None


# 定义函数：把裁判层 JSON 结果写入 game_state，并打印给玩家看
def apply_jingzhou_eval_result(game_state: dict, eval_result: dict) -> None:
    if eval_result.get("relevance") == "none":
        print("（荆州线：本轮话题与刘表/荆州关联较弱，数值基本不变。）\n")
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
        jz[_f] = _new[_f]
    # （v11：上面已用循环原子写入，此处不再逐字段赋值）
    relevance = eval_result.get("relevance", "?")
    reason = eval_result.get("causal_reason", "")
    stance = eval_result.get("liubei_inner_stance", "")
    print(f"（荆州线·因果[{relevance}] {reason}）")
    if stance:
        print(f"（刘备内心：{stance}）")
    print(
        f"（数值更新）刘表信任 {jz['liu_biao_trust']} | "
        f"荆州想法 {jz['jingzhou_interest']} | "
        f"托孤接受 {jz['tuogu_acceptance']} | "
        f"照拂二子 {jz['qi_cong_care']} | "
        f"推辞倾向 {jz['ren_defer_tendency']}\n"
    )


# 定义函数：刘表 NPC 预托事件（由 AI 裁判判定触发，非固定阈值硬编码）
def maybe_trigger_liubiao_tuogu_event(game_state: dict, eval_result: dict) -> None:
    # ---- v11 修改：严格判断 True。原版 `if not ...` 会让字符串 "false" 误触发 ----
    if eval_result.get("tuogu_event_trigger") is not True:
        return
    if game_state["liubiao_npc"]["tuogu_offered"]:
        return
    game_state["liubiao_npc"]["tuogu_offered"] = True
    jz = game_state["jingzhou"]
    defer = jz["ren_defer_tendency"]
    if defer >= 55:
        stance_hint = "刘备更可能谦虚推辞，以名节为先"
    else:
        stance_hint = "刘备更可能当仁不让，以安荆保孤为名"
    print("\n" + "═" * 20 + " 【荆州事件·刘表预托】 " + "═" * 20)
    print("【刘表】（病榻，背景 NPC）")
    print(
        "「玄德，琦、琮年幼，蔡党日盛……荆州之地，老夫能托于谁？"
        "你连日照拂，老夫心已知之。」"
    )
    print(f"（系统：托孤议题已开启。当前刘备倾向判断：{stance_hint}。）")
    print("（你可继续选刘备，用下一句话影响其「接受」或「推辞」。）")
    print("═" * 52 + "\n")


# 定义函数：在回合状态面板中展示荆州线与刘表 NPC 简报
def show_jingzhou_status(game_state: dict) -> None:
    jz = game_state["jingzhou"]
    npc = game_state["liubiao_npc"]
    tuogu_flag = "已预托" if npc["tuogu_offered"] else "未触发"
    print(
        "【荆州·NPC】刘表守土 | "
        f"刘表信任 {jz['liu_biao_trust']} | "
        f"刘备荆州想法 {jz['jingzhou_interest']} | "
        f"托孤接受 {jz['tuogu_acceptance']} | "
        f"照拂二子 {jz['qi_cong_care']} | "
        f"推辞倾向 {jz['ren_defer_tendency']} | "
        f"预托事件 {tuogu_flag}"
    )


# 定义函数：打印当前回合数与三方势力状态面板
def show_round_briefing(round_number: int, histories: dict, game_state: dict) -> None:
    # 打印回合标题
    print(f"\n════════ 第 {round_number} 回合 ════════")
    # 打印年份与玩法提示
    print("公元207年 · 三国鼎立前夕（原型状态面板）")
    # 依次打印曹操、孙权、刘备的状态行
    for role_key in ("曹操", "孙权", "刘备"):
        print(format_faction_status(role_key, histories[role_key]))
    # 展示荆州线与刘表 NPC 相关数值（刘备对话会由 AI 裁判更新）
    show_jingzhou_status(game_state)
    print()


# 定义函数：打印本回合未被选中的角色处于「观察」状态
def show_observers(active_role: str, all_roles: tuple) -> None:
    # 遍历三位君主，找出不是本轮对话对象的名字
    observers = [name for name in all_roles if name != active_role]
    # 将观察者名单用顿号连接成字符串
    observer_text = "、".join(observers)
    # 说明他们本回合没有参与对话，下回合可再选
    print(f"（{observer_text} 本回合保持观察，下回合你可选择与他们对话。）\n")


# 定义函数：裁剪对话历史，只保留最近 max_rounds 轮，防止发给模型的上下文过长
def trim_chat_history(history: list, max_rounds: int) -> list:
    # 一轮对话包含 2 条消息（user + assistant），所以最多保留 max_rounds * 2 条
    max_messages = max_rounds * 2
    # 若当前条数未超限，原样返回；否则只取列表末尾的 max_messages 条（最近的对话）
    if len(history) <= max_messages:
        return history
    return history[-max_messages:]


# 定义函数：带超时自动重试的 API 调用（演示现场网络波动时提高成功率）
def create_chat_completion_with_retry(**kwargs):
    # 记录最后一次异常，全部失败后抛出
    last_error = None
    # 第 1 次 + 最多 API_MAX_RETRIES 次重试
    for attempt in range(API_MAX_RETRIES + 1):
        try:
            # 非首次尝试时提示观众/演示者正在重试
            if attempt > 0:
                print(
                    f"（API 超过 {API_RETRY_TIMEOUT_SECONDS} 秒无响应，"
                    f"正在第 {attempt + 1} 次重试……）",
                    flush=True,
                )
            # 每次请求单独设置较短超时，便于快速触发重试
            return get_client().with_options(
                timeout=API_RETRY_TIMEOUT_SECONDS
            ).chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            # 仅超时进入重试；其他错误直接抛出
            last_error = exc
            if attempt >= API_MAX_RETRIES:
                break
    # 所有尝试均超时，抛出最后一次异常供上层处理
    raise last_error


# 定义通用函数：任意 AI 角色根据人设与独立历史回复玩家
def ask_character(
    player_command: str,
    chat_history: list,
    persona: str,
) -> str:
    # 先根据上限裁剪该角色自己的历史，互不干扰
    recent_history = trim_chat_history(chat_history, MAX_HISTORY_ROUNDS)
    # 组装消息：system 人设 + 该角色历史 + 本轮玩家输入
    messages = [
        {"role": "system", "content": persona},
        *recent_history,
        {"role": "user", "content": player_command},
    ]
    # 调用 DeepSeek 聊天接口（含超时重试）
    response = create_chat_completion_with_retry(
        model="deepseek-chat",
        messages=messages,
        max_tokens=150,
        temperature=0.8,
    )
    # 返回模型生成的一句台词
    return response.choices[0].message.content.strip()


# 定义函数：把本轮「玩家话 + AI 回复」写入某个角色的 chat_history，并裁剪长度
def save_to_history(chat_history: list, player_command: str, reply: str) -> None:
    # 追加玩家输入，role 为 user
    chat_history.append({"role": "user", "content": player_command})
    # 追加该 AI 的回复，role 为 assistant
    chat_history.append({"role": "assistant", "content": reply})
    # 原地更新列表，只保留最近 MAX_HISTORY_ROUNDS 轮
    chat_history[:] = trim_chat_history(chat_history, MAX_HISTORY_ROUNDS)


# 定义函数：向指定角色发起一次对话；刘备时可传入 game_state 以启用荆州线 AI 因果评估
def speak_with_character(
    role_name: str,
    persona: str,
    player_command: str,
    chat_history: list,
    game_state: dict | None = None,
) -> bool:
    try:
        # 显示正在向哪位角色请求，flush 立刻输出到终端
        print(f"（{role_name}正在思索，正在连接 DeepSeek……）", flush=True)
        # 刘备且传入 game_state 时，注入动态荆州态势（不改 LIUBEI_PERSONA 常量本体）
        effective_persona = persona
        if role_name == "刘备" and game_state is not None:
            effective_persona = build_liubei_system_prompt(game_state)
        # 调用通用问答函数
        reply = ask_character(player_command, chat_history, effective_persona)
        # 写入该角色独立的历史
        save_to_history(chat_history, player_command, reply)
        # 打印带角色名的台词
        print(f"{role_name}：{reply}\n")
        # 仅在与刘备对话后：由 AI 裁判评估因果并更新荆州线数值
        if role_name == "刘备" and game_state is not None:
            eval_result = evaluate_liubei_jingzhou_causality(
                player_command, reply, game_state, chat_history
            )
            if eval_result is not None:
                apply_jingzhou_eval_result(game_state, eval_result)
                maybe_trigger_liubiao_tuogu_event(game_state, eval_result)
        return True
    except APITimeoutError:
        print(
            f"调用失败：{role_name} 请求超时"
            f"（单次 {API_RETRY_TIMEOUT_SECONDS} 秒，已重试 {API_MAX_RETRIES} 次）。\n"
        )
        return False
    except APIConnectionError as e:
        print(f"调用失败：无法连接 DeepSeek（{e}）。\n")
        return False
    except APIStatusError as e:
        print(f"调用失败：API 返回错误（HTTP {e.status_code}）。详情：{e}\n")
        return False
    except KeyboardInterrupt:
        print("\n已中断。本回合可重新选择，或输入 quit 退出。\n")
        return False
    except Exception as e:
        print(f"调用失败：{e}\n")
        return False


# 定义函数：判断玩家是否要退出游戏
def is_quit_command(text: str) -> bool:
    # 统一转小写后匹配英文退出词，或匹配中文退出词
    return text.lower() in ("quit", "exit", "q") or text in ("退出", "再见")


# 定义函数：解析玩家选择的对话对象，返回角色键名；无法识别时返回 None
def parse_role_choice(choice: str) -> str | None:
    # 去掉首尾空格，并转成小写，方便匹配英文简写
    normalized = choice.strip().lower()
    # 用字典映射：多种输入方式 → 统一的角色键名
    mapping = {
        "1": "曹操",
        "曹操": "曹操",
        "caocao": "曹操",
        "cao": "曹操",
        "2": "孙权",
        "孙权": "孙权",
        "sunquan": "孙权",
        "sun": "孙权",
        "3": "刘备",
        "刘备": "刘备",
        "liubei": "刘备",
        "liu": "刘备",
    }
    # 若输入在映射表中，返回对应角色名；否则返回 None
    return mapping.get(normalized) or mapping.get(choice.strip())


# 定义常量：三位君主的名字顺序，用于遍历与显示观察者
ALL_ROLES = ("曹操", "孙权", "刘备")

# 定义字典：把角色键名绑定到人设 Prompt，供 speak_with_character 调用
ROLE_PERSONAS = {
    "曹操": CAOCAO_PERSONA,
    "孙权": SUNQUAN_PERSONA,
    "刘备": LIUBEI_PERSONA,
}

# 汇总层 Prompt：前半中立提炼分歧，后半以曹/孙/刘口吻各「逼问」玩家；仅改此常量即可调优
STRATEGIC_BRIEFING_PROMPT = (
    "当前时间为公元207年。你负责撰写《207年局势简评》，分两段完成：\n"
    "· 前半「三方核心分歧」：用中立顾问口吻客观概括，不代入任何君主说话。\n"
    "· 后半「三方逼问」：分别用曹操、孙权、刘备的口吻与性格，各向玩家逼问一句（可带威胁、试探或恳切）。\n\n"
    "玩家提出的战略问题是：\n{question}\n\n"
    "以下是三位当事人对此问题的回答原文：\n"
    "【曹操】{reply_caocao}\n"
    "【孙权】{reply_sunquan}\n"
    "【刘备】{reply_liubei}\n\n"
    "请严格按下列格式输出（不要增减章节标题，不要在中途插入顾问点评）：\n\n"
    "============ 《207年局势简评》 ============\n"
    "三方核心分歧：（用2-3句话总括，点明各方立场之间的核心张力）\n"
    "➊ 曹操认为……\n"
    "➋ 孙权主张……\n"
    "➌ 刘备倾向……\n\n"
    "──── 三方逼问 ────\n"
    "【曹操逼问你】（用曹操第一人称：多疑、霸气、爱才但戒备；可施压、冷笑、威胁；"
    "207年北方霸主，勿称他人为帝；勿提207年后史实）\n"
    "【孙权逼问你】（用孙权第一人称：沉稳、审时度势、江东之主姿态；"
    "自称可用江东/孙氏/本将军；禁止「吴国」「寡人」「朕」；勿提207年后史实）\n"
    "【刘备逼问你】（用刘备第一人称：仁义、坚韧、势弱但有志；可对玩家称「主公」；"
    "可表露对联吴的戒心；禁止「蜀王」「蜀国」；勿提赤壁战后及207年后史实）\n\n"
    "逼问段落范例（须结合本题与三人原话重写，勿照抄）：\n"
    "【曹操逼问你】你当真以为，与孙权结盟就能安枕无忧？他今日助你，明日便可反咬一口。"
    "你若执意联吴，休怪我大军压境时，不留情面。\n"
    "【孙权逼问你】你刘玄德如今兵不过万，将不过关张，与我结盟不过是权宜之计。"
    "我且问你——若日后荆州归你，你拿什么来换我江东的庇护？\n"
    "【刘备逼问你】主公，孙权虽可暂为盟友，然此人心机深沉，我恐他日后反客为主。"
    "您当真放心把侧翼交给他？\n\n"
    "硬性要求：\n"
    "· 「三方逼问」段必须角色扮演，与前半中立概括无关；即便其他指令要求不扮演人物，逼问段仍须用各君主口吻。\n"
    "· 每位君主的逼问须2-4句，必须是向玩家发出的质问/试探，禁止替玩家做决定。\n"
    "· 禁止输出中立谋士口吻的编号反问（如「1. 您心中孰轻孰重？」）；逼问段只能有上述三个【××逼问你】标题。\n"
    "· 禁止「下一步建议」「行动清单」；➊➋➌ 须忠实反映三人原意并点出矛盾。\n"
    "· 不要编造207年之后的历史；全文中文；简练，总篇幅不宜超过一屏。"
)


# 定义函数：根据三人回答，调用 DeepSeek 生成辅助决策简评（分歧摘要 + 反问，非长篇报告）
def generate_strategic_briefing(question: str, replies: dict) -> str:
    # 用三人原文填充简评 Prompt 模板
    user_content = STRATEGIC_BRIEFING_PROMPT.format(
        question=question,
        reply_caocao=replies["曹操"],
        reply_sunquan=replies["孙权"],
        reply_liubei=replies["刘备"],
    )
    # 单独一次 API 调用（含超时重试）：system 强调顾问身份，user 携带问题与三人回答
    response = create_chat_completion_with_retry(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": (
                    "你是207年三国局势的战略顾问，只输出分析报告，"
                    "不扮演任何历史人物，不用古风台词。"
                ),
            },
            {"role": "user", "content": user_content},
        ],
        # 输出为短格式分歧+逼问，token 上限适中即可
        max_tokens=450,
        # 略降低随机性，让分析更稳定、更像参谋报告
        temperature=0.5,
    )
    # 返回顾问报告正文
    return response.choices[0].message.content.strip()


# 定义函数：一题三答 + 局势简评（核心战略咨询流程）
def strategic_consult(question: str, histories: dict) -> dict | None:
    # 用字典收集三位君主的回答，键为角色名，值为台词原文
    replies = {}
    # 按固定顺序依次询问曹操、孙权、刘备
    for role_name in ALL_ROLES:
        try:
            # 提示当前正在询问哪一位（战略咨询模式下一连问三人）
            print(f"（战略咨询：正在询问{role_name}……）", flush=True)
            # 使用该角色的人设与独立 chat_history 生成回答（与单回合对话逻辑相同）
            reply = ask_character(
                question,
                histories[role_name],
                ROLE_PERSONAS[role_name],
            )
            # 写入该角色记忆，使后续单回合对话也能记住此次战略咨询
            save_to_history(histories[role_name], question, reply)
            # 存入 replies 供简评与返回值使用
            replies[role_name] = reply
            # 在终端展示该角色的回答
            print(f"{role_name}：{reply}\n")
        except APITimeoutError:
            print(
                f"战略咨询失败：询问{role_name}时超时"
                f"（单次 {API_RETRY_TIMEOUT_SECONDS} 秒，已重试 {API_MAX_RETRIES} 次）。\n"
            )
            return None
        except APIConnectionError as e:
            print(f"战略咨询失败：询问{role_name}时无法连接（{e}）。\n")
            return None
        except APIStatusError as e:
            print(f"战略咨询失败：询问{role_name}时 API 错误（HTTP {e.status_code}）。\n")
            return None
        except KeyboardInterrupt:
            print("\n战略咨询已中断。\n")
            return None
        except Exception as e:
            print(f"战略咨询失败：询问{role_name}时出错（{e}）。\n")
            return None

    try:
        # 三人回答齐全后，再调用一次 DeepSeek 生成局势简评
        print("（战略咨询：正在汇总三方观点，撰写局势简评……）", flush=True)
        briefing = generate_strategic_briefing(question, replies)
    except APITimeoutError:
        print(
            f"局势简评生成失败：请求超时"
            f"（单次 {API_RETRY_TIMEOUT_SECONDS} 秒，已重试 {API_MAX_RETRIES} 次）。\n"
        )
        return None
    except APIConnectionError as e:
        print(f"局势简评生成失败：无法连接（{e}）。\n")
        return None
    except APIStatusError as e:
        print(f"局势简评生成失败：API 错误（HTTP {e.status_code}）。\n")
        return None
    except KeyboardInterrupt:
        print("\n局势简评生成已中断。\n")
        return None
    except Exception as e:
        print(f"局势简评生成失败：{e}\n")
        return None

    # 返回结构化结果，便于主循环打印或后续扩展（存档、UI 等）
    return {
        "question": question,
        "replies": replies,
        "briefing": briefing,
    }


# 定义函数：判断玩家是否选择「战略咨询 / 一题三答」模式
def is_strategic_consult_choice(choice: str) -> bool:
    # 统一成小写，方便匹配英文
    normalized = choice.strip().lower()
    # 多种别名都视为进入战略咨询
    return normalized in ("4", "咨询", "战略", "consult", "brief", "简评")


# 定义函数：回合事件触发器——按概率自动召开军议，内部调用现有 strategic_consult
def try_auto_war_council(histories: dict) -> bool:
    # 生成 0~1 之间随机数，若大于等于阈值则本回合不触发军议
    if random.random() >= WAR_COUNCIL_PROBABILITY:
        return False
    # 从预设议题中随机抽取一条：(军议场面描述, 战略问题正文)
    event_desc, council_question = random.choice(WAR_COUNCIL_TOPICS)
    # 打印系统事件开场，作为本回合开场剧情
    print(f"\n【系统事件：军议——{event_desc}……】")
    print(f"军议议题：{council_question}\n")
    # 调用既有战略咨询流程：自动问曹操、孙权、刘备并生成局势简评
    consult_result = strategic_consult(council_question, histories)
    # 若 API 全程成功，打印完整军议内容（含分歧与三方逼问）
    if consult_result is not None:
        print_strategic_consult_result(consult_result)
        # 军议收场提示，随后主循环仍等待玩家选角对话
        print("──── 军议结束，请主公指示 ────\n")
        return True
    # 若中途失败，提示玩家仍可照常操作，不结束本回合
    print("（军议因故中断，你仍可照常选择对话对象。）\n")
    return False


# 定义函数：在终端打印 strategic_consult 的返回结果（标题与正文由汇总层 Prompt 统一格式输出）
def print_strategic_consult_result(result: dict) -> None:
    # 直接打印顾问层正文（已含《207年局势简评》标题与「请主公思量」等结构）
    print("\n" + result["briefing"] + "\n")


# 定义函数：游戏结束时三位君主依次告别
def print_farewell() -> None:
    # 曹操告别语
    print("曹操：孟德暂且告退。来日再叙。")
    # 孙权告别语
    print("孙权：仲谋亦当收兵，他日再会。")
    # 刘备告别语
    print("刘备：玄德告辞，愿他日再与使君共论天下。")


# 定义函数：判断玩家是否输入隐藏重置命令（演示卡死时应急回到主菜单）
def is_reset_command(text: str) -> bool:
    # 去掉首尾空格后，精确匹配 !reset
    return text.strip() == "!reset"


# 定义函数：清空游戏状态，相当于重新开始
def reset_game_state(histories: dict, game_state: dict) -> None:
    # 遍历三位君主，清空各自对话记忆列表
    for role_key in histories:
        histories[role_key].clear()
    # 荆州线数值与刘表事件标记恢复初始值
    game_state.clear()
    game_state.update(create_initial_game_state())


# 定义函数：打印主菜单欢迎语与操作说明
def print_welcome() -> None:
    # 打印游戏标题
    print("\n=== 魏 · 吴 · 备 · 三角对话（AI 历史策略原型）===")
    print(f"每位角色各自记住最近 {MAX_HISTORY_ROUNDS} 轮与你的对话。")
    print("每一回合：查看三方状态 → 选择一位对话 → 另两位本回合观察。")
    print("选择方式：输入 1/曹操、2/孙权、3/刘备。")
    print("战略咨询：输入 4 或 咨询 → 手动召开军议（一题三答）。")
    print(f"每回合有 {int(WAR_COUNCIL_PROBABILITY * 100)}% 概率自动触发「军议」开场事件。")
    print("演示应急：任意输入处键入 !reset 可清空状态并回到主菜单。")
    print("荆州线：与刘备聊刘表/荆州时，AI 裁判会自动评估因果并更新托孤等数值。")
    print("输入 quit 或 退出 结束。等待 API 时请勿连打，可用 Ctrl+C 中断。\n")


# 定义函数：打印演示模式分步解说标题（--demo 时向教授讲解每一步）
def print_demo_step(step_no: int, title: str, detail: str) -> None:
    # 用醒目分隔线标出演示阶段
    print("\n" + "█" * 56)
    print(f"  【演示步骤 {step_no}】{title}")
    print(f"  → {detail}")
    print("█" * 56 + "\n")


# 定义函数：一键演示模式（--demo），自动跑完军议 + 手动战略咨询全流程
def run_demo_mode() -> None:
    # 演示用独立记忆，不影响你平时测试存档（本进程内）
    histories = {
        "曹操": [],
        "孙权": [],
        "刘备": [],
    }
    # 演示开场白
    print("\n" + "=" * 20 + " 面试演示模式 " + "=" * 20)
    print("本模式将自动执行：自动军议 → 手动战略咨询 → 一题三答 + 三方逼问")
    print("全程无需手动输入。Ctrl+C 可中断。\n")

    # 步骤 1：模拟「自动军议」事件（不修改 try_auto_war_council，仅复用其调用方式）
    print_demo_step(
        1,
        "自动军议事件",
        "系统随机议题，自动调用 strategic_consult（三 Agent + 汇总层）",
    )
    # 取预设军议第一条作为演示议题（与 try_auto_war_council 使用同一议题表）
    event_desc, council_question = WAR_COUNCIL_TOPICS[0]
    print(f"【系统事件：军议——{event_desc}……】")
    print(f"军议议题：{council_question}\n")
    # 调用既有战略咨询核心函数（逻辑未改）
    war_result = strategic_consult(council_question, histories)
    if war_result is None:
        print("（演示中断：自动军议 API 调用失败。）\n")
        return
    print_strategic_consult_result(war_result)
    print("──── 军议结束 ────\n")

    # 步骤 2：模拟玩家选择「4 战略咨询」并自动提问
    print_demo_step(
        2,
        "手动战略咨询",
        f'模拟玩家输入选项 4，议题：「{DEMO_MANUAL_QUESTION}」',
    )
    print(f"【战略咨询】玩家提问> {DEMO_MANUAL_QUESTION}\n")
    manual_result = strategic_consult(DEMO_MANUAL_QUESTION, histories)
    if manual_result is None:
        print("（演示中断：手动战略咨询 API 调用失败。）\n")
        return
    print_strategic_consult_result(manual_result)

    # 步骤 3：演示收尾
    print_demo_step(
        3,
        "演示完成",
        "已展示：多 Agent 独立作答 + 汇总层分歧分析 + 三方口吻逼问",
    )
    print("可运行 python demo_script.py 生成 PPT 用终端截图 strategic_consult_demo.png\n")


# 定义函数：主游戏循环（支持 !reset 回到干净主菜单）
def run_game_loop() -> None:
    # 外层循环：!reset 时 break 内层后重新初始化
    while True:
        # 用字典统一管理三位角色的对话记忆
        histories = {
            "曹操": [],
            "孙权": [],
            "刘备": [],
        }
        # 荆州线 / 刘表 NPC 相关全局状态
        game_state = create_initial_game_state()
        # 回合计数器
        round_number = 0
        # 打印欢迎语
        print_welcome()

        # 内层循环：正常回合制游戏
        while True:
            # 进入新回合，回合号加 1
            round_number += 1
            # 展示当前回合数与三方势力基本状态（含荆州线）
            show_round_briefing(round_number, histories, game_state)

            # 回合事件：20% 概率自动军议（调用 strategic_consult，不替代后续玩家选角）
            try_auto_war_council(histories)

            # 读取玩家选择的对话对象或战略咨询模式
            choice_input = input(
                "请选择（1曹操 / 2孙权 / 3刘备 / 4战略咨询，或 quit 退出）> "
            ).strip()

            # 隐藏命令：!reset 清空状态并回到主菜单
            if is_reset_command(choice_input):
                reset_game_state(histories, game_state)
                print("\n【!reset】已清空全部对话记忆与荆州线状态，回到主菜单。\n")
                break

            # 若玩家要退出，打印告别并结束整个程序
            if is_quit_command(choice_input):
                print_farewell()
                return

            # 若直接回车未选择，提示并回退回合号，不消耗本回合
            if not choice_input:
                print("（未选择对话对象，本回合跳过。）\n")
                round_number -= 1
                continue

            # 若选择战略咨询：一题三答 + 局势简评（不进入单角色对话分支）
            if is_strategic_consult_choice(choice_input):
                # 读取玩家提出的战略问题
                consult_question = input("【战略咨询】请输入战略问题> ").strip()

                # 战略咨询输入框也支持 !reset
                if is_reset_command(consult_question):
                    reset_game_state(histories, game_state)
                    print("\n【!reset】已清空全部对话记忆与荆州线状态，回到主菜单。\n")
                    break

                # 若未输入问题，跳过本回合
                if not consult_question:
                    print("（未输入战略问题，本回合跳过。）\n")
                    round_number -= 1
                    continue
                # 若在输入问题时选择退出
                if is_quit_command(consult_question):
                    print_farewell()
                    return
                # 调用战略咨询核心函数（自动问三人 + 生成简评）
                consult_result = strategic_consult(consult_question, histories)
                # 若成功，打印《207年局势简评》；失败时 strategic_consult 已打印错误信息
                if consult_result is not None:
                    print_strategic_consult_result(consult_result)
                else:
                    # API 中途失败时回退回合号，便于重试
                    round_number -= 1
                # 手动战略咨询占满本回合
                print("—— 本回合结束（战略咨询）——\n")
                continue

            # 把输入解析成「曹操」「孙权」「刘备」之一
            active_role = parse_role_choice(choice_input)
            # 若输入无法识别，提示合法选项并回退回合号
            if active_role is None:
                print("无法识别选择，请输入 1、2、3、4 或 曹操/孙权/刘备/咨询。\n")
                round_number -= 1
                continue

            # 读取你对该角色说的话
            player_command = input(f"【对{active_role}】> ").strip()

            # 单角色对话输入框也支持 !reset
            if is_reset_command(player_command):
                reset_game_state(histories, game_state)
                print("\n【!reset】已清空全部对话记忆与荆州线状态，回到主菜单。\n")
                break

            # 若未输入内容，跳过本回合
            if not player_command:
                print("（未输入指令，本回合跳过。）\n")
                round_number -= 1
                continue

            # 若在输入指令时选择退出
            if is_quit_command(player_command):
                print_farewell()
                return

            # 与选中的角色对话；使用该角色独立的历史与人设
            success = speak_with_character(
                active_role,
                ROLE_PERSONAS[active_role],
                player_command,
                histories[active_role],
                game_state if active_role == "刘备" else None,
            )
            # 若 API 失败，回退回合号，便于你重试同一「第 N 回合」
            if not success:
                round_number -= 1
                continue

            # 显示另外两位本回合处于观察状态
            show_observers(active_role, ALL_ROLES)

            # 本回合结束分隔线
            print("—— 本回合结束 ——\n")


# 定义函数：解析命令行参数
def parse_cli_args():
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description="207年三国 AI 策略对话原型（终端版）",
    )
    # --demo：一键自动演示，适合面试现场
    parser.add_argument(
        "--demo",
        action="store_true",
        help="面试演示模式：自动军议 + 手动战略咨询，无需手动输入",
    )
    return parser.parse_args()


# 仅当直接运行本文件时执行下面代码（被 import 时不会执行）
if __name__ == "__main__":
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
        dump_legality()
