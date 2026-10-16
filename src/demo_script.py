# -*- coding: utf-8 -*-
# 一键生成「战略咨询」终端风格截图，供 PPT 插入使用

# 从标准库导入 io、sys，用于捕获终端输出
import io
import sys

# 从标准库导入 os，用于拼接输出路径与查找字体
import os

# 从 Pillow 导入绘图模块，把文字渲染成 PNG 图片
from PIL import Image, ImageDraw, ImageFont

# 从主程序导入战略咨询相关函数与演示议题（不修改主程序核心逻辑）
from caocao_deepseek import (
    DEMO_MANUAL_QUESTION,
    print_strategic_consult_result,
    strategic_consult,
)

# 输出图片文件名（与任务要求一致）
OUTPUT_PNG = "strategic_consult_demo.png"

# 图片宽度（高清，适合 PPT 全屏或半屏插图）
IMAGE_WIDTH = 1920

# 左右边距（像素）
PADDING_X = 48

# 上下边距（像素）
PADDING_Y = 40

# 行高（像素，字号大时行距也要加大）
LINE_HEIGHT = 42

# 终端绿字颜色（经典黑客终端风格）
TERMINAL_GREEN = "#33FF66"

# 纯黑背景
TERMINAL_BLACK = "#0A0A0A"


# 定义类：同时把 print 内容写到终端和内存列表，便于后续制图
class TeeWriter(io.StringIO):
    def __init__(self, terminal, buffer: list):
        # 保存真实终端流（stdout）
        self.terminal = terminal
        # 保存按行累积的文本列表
        self.buffer = buffer

    def write(self, text: str) -> int:
        # 同步输出到真实终端，演示时仍能看到进度
        self.terminal.write(text)
        # 按换行拆成多行写入 buffer
        for line in text.splitlines(keepends=True):
            if line.endswith("\n"):
                self.buffer.append(line.rstrip("\n"))
            elif line:
                if self.buffer:
                    self.buffer[-1] = self.buffer[-1] + line
                else:
                    self.buffer.append(line)
        return len(text)

    def flush(self) -> None:
        self.terminal.flush()


# 定义函数：在 macOS / 常见系统上寻找支持中文的等宽或黑体字体
def load_terminal_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # 候选字体路径（按优先级排列）
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    # 若都找不到，退回 Pillow 默认字体（可能无法显示全部中文）
    return ImageFont.load_default()


# 定义函数：按像素宽度自动换行（适配中文逐字折行）
def wrap_text_line(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list:
    if not text:
        return [""]
    lines = []
    current = ""
    for char in text:
        trial = current + char
        # textlength 计算当前行像素宽度
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


# 定义函数：把多行终端文本渲染为黑底绿字 PNG
def render_terminal_png(lines: list[str], output_path: str) -> None:
    # 字号加大，PPT 投影更清晰
    font_size = 28
    font = load_terminal_font(font_size)
    # 创建临时画布用于测量文字宽度
    measure_img = Image.new("RGB", (IMAGE_WIDTH, 100), TERMINAL_BLACK)
    measure_draw = ImageDraw.Draw(measure_img)
    max_text_width = IMAGE_WIDTH - 2 * PADDING_X
    # 对所有行做自动换行
    wrapped_lines = []
    for line in lines:
        wrapped_lines.extend(wrap_text_line(measure_draw, line, font, max_text_width))
    # 根据总行数计算图片高度
    image_height = PADDING_Y * 2 + LINE_HEIGHT * max(len(wrapped_lines), 1)
    # 创建最终黑底图像
    image = Image.new("RGB", (IMAGE_WIDTH, image_height), TERMINAL_BLACK)
    draw = ImageDraw.Draw(image)
    # 逐行绘制绿色文字
    y = PADDING_Y
    for line in wrapped_lines:
        draw.text((PADDING_X, y), line, fill=TERMINAL_GREEN, font=font)
        y += LINE_HEIGHT
    # 保存为 PNG（高清，适合 PPT）
    image.save(output_path, format="PNG")
    print(f"\n✓ 已保存终端风格截图：{os.path.abspath(output_path)}")


# 定义函数：运行一次战略咨询并收集终端输出
def run_and_capture_strategic_consult() -> list[str]:
    # 独立记忆，避免污染你平时的测试状态
    histories = {
        "曹操": [],
        "孙权": [],
        "刘备": [],
    }
    # 截图顶部说明行（纯展示，不调用 API）
    captured = [
        "=== 207年三国 AI 战略咨询 · 演示截图 ===",
        f"议题：{DEMO_MANUAL_QUESTION}",
        "",
    ]
    # 用 TeeWriter 接管 stdout，捕获 strategic_consult 的全部 print
    tee = TeeWriter(sys.stdout, captured)
    old_stdout = sys.stdout
    sys.stdout = tee
    try:
        # 调用主程序既有战略咨询流程（一题三答 + 汇总逼问）
        result = strategic_consult(DEMO_MANUAL_QUESTION, histories)
        if result is not None:
            print_strategic_consult_result(result)
        else:
            captured.append("（战略咨询失败，请检查 DEEPSEEK_API_KEY 与网络。）")
    finally:
        # 恢复标准输出
        sys.stdout = old_stdout
    return captured


# 定义脚本入口：一键运行 → API 咨询 → 保存 PNG
def main() -> None:
    print("正在运行战略咨询并生成 PPT 截图，请稍候（约 4 次 API 调用）……\n")
    lines = run_and_capture_strategic_consult()
    render_terminal_png(lines, OUTPUT_PNG)


# 仅当直接运行本文件时执行
if __name__ == "__main__":
    main()
