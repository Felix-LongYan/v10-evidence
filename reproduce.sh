#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "需要 Python 3.12 或更新版本。" >&2
  exit 1
fi

# -I 隔离外部 Python 配置；-B 不在证据目录内生成字节码缓存。
python3 -I -B - "$ROOT" <<'PY'
import ast
import contextlib
import io
import os
from pathlib import Path
import runpy
import sys
import types

if sys.version_info < (3, 12):
    raise SystemExit("需要 Python 3.12 或更新版本。")
sys.stdout.reconfigure(encoding="utf-8")
root = Path(sys.argv[1]).resolve()

# 四项检验只使用本地状态函数。占位模块仅满足原程序的顶层导入，
# 不提供模型输出；任何客户端构造和网络操作都会立即失败。
for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
    os.environ.pop(name, None)

def deny_api(*args, **kwargs):
    raise RuntimeError("离线核验禁止构造 API 客户端。")

offline_openai = types.ModuleType("openai")
offline_openai.OpenAI = deny_api
for name in ("APIConnectionError", "APITimeoutError", "APIStatusError"):
    setattr(offline_openai, name, type(name, (Exception,), {}))
sys.modules["openai"] = offline_openai

def deny_network(event, args):
    if event.startswith("socket."):
        raise RuntimeError("离线核验禁止网络操作。")

sys.addaudithook(deny_network)

print("[1/4] 两个版本的 Python 语法检查")
for name in ("caocao_deepseek.py", "caocao_deepseek_v11.py"):
    path = root / "src" / name
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"  OK: src/{name}")

print("\n[2/4] 四项约束检验（--both；离线，无 API key）")
namespace = runpy.run_path(str(root / "tools" / "constraint_demo.py"))
main = namespace["main"]
original_report = main.__globals__["report"]
observed = []

def collect_report(label, module):
    result = original_report(label, module)
    observed.append((label, result))
    return result

main.__globals__["report"] = collect_report
sys.argv = ["constraint_demo.py", "--both", "--path", str(root / "src")]
buffer = io.StringIO()
try:
    with contextlib.redirect_stdout(buffer):
        status = main()
        if status != 0 or len(observed) != 2:
            raise RuntimeError("约束检验未完整运行两个版本。")
        keys = {"delta", "trigger", "atomic", "logging"}
        for index, (label, result) in enumerate(observed):
            if set(result) != keys or any(type(v) is not bool for v in result.values()):
                raise RuntimeError(f"检验缺失或出现异常结果：{label}：{result}")
            passed = sum(result.values())
            print(f"{label}：{passed}/4")
            expected = index == 1
            if any(value is not expected for value in result.values()):
                raise RuntimeError(f"与既定四项验收结果不符：{label}：{result}")
finally:
    output = buffer.getvalue()
    (root / "evidence" / "constraint_verify.log").write_text(output, encoding="utf-8")
    print(output, end="", flush=True)

def line_count(path):
    with path.open("rb") as handle:
        return sum(1 for _ in handle)

print("\n[3/4] 历史 results.csv 行数（均含表头）")
csv_paths = sorted((root / "testbed" / "runs").rglob("results.csv"))
if not csv_paths:
    raise RuntimeError("缺少 testbed/runs/ 下的 results.csv。")
primary = root / "testbed" / "runs" / "run-20261015-1607" / "results.csv"
for path in csv_paths:
    count = line_count(path)
    mark = " [主运行，应为 541]" if path == primary else ""
    print(f"  {path.relative_to(root)}: {count} 行{mark}")
if not primary.is_file() or line_count(primary) != 541:
    raise RuntimeError("主运行 results.csv 行数应为 541（含表头）。")

print("\n[4/4] 历史演示日志行数")
demo = root / "evidence" / "demo_run.log"
count = line_count(demo)
print(f"  evidence/demo_run.log: {count} 行 [应为 77]")
if count != 77:
    raise RuntimeError("demo_run.log 行数应为 77。")

print("\n全部离线核验通过；约束输出已保存至 evidence/constraint_verify.log。")
PY
