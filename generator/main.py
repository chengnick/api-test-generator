"""
main.py — 主程式

用法：
    python main.py                    # 產生所有 target 的測試腳本
    python main.py httpbin            # 只產生指定 target
    python main.py --list             # 列出可用的 target

產生完成後：
    pytest generated_tests/ -v
"""

from __future__ import annotations

import asyncio
import sys
import time

from config import TARGETS, GENERATOR, MAX_CONCURRENT, ERROR_STATUS
from discovery import from_spec
from test_generator import generate_pytest_script


def _fmt_dur(sec: float) -> str:
    """90.5 → '1m30s'；45.2 → '45.2s'"""
    if sec < 60:
        return f"{sec:.1f}s"
    m, s = divmod(int(round(sec)), 60)
    return f"{m}m{s:02d}s"


async def run_unit(target: str, cfg: dict, semaphore: asyncio.Semaphore) -> dict:
    """處理單一 target：探索 endpoint → 產生腳本"""
    async with semaphore:
        t0 = time.perf_counter()
        print(f"\n{'=' * 60}\n[{target}] 🎯 開始：{cfg['base_url']}\n{'=' * 60}")

        pre, post = from_spec(cfg["spec"])

        filepath = generate_pytest_script(
            target=target,
            base_url=cfg["base_url"],
            login_name=cfg.get("login_name", ""),
            password=cfg.get("password", ""),
            pre_login_apis=pre,
            post_login_apis=post,
            auth_type=cfg.get("auth_type", "basic"),
            error_status=ERROR_STATUS,
            timeout=GENERATOR["timeout"],
            output_dir=GENERATOR["output_dir"],
        )

        elapsed = time.perf_counter() - t0
        print(f"[{target}] 📄 {filepath} | {len(pre)}+{len(post)} 支 | {_fmt_dur(elapsed)}")

        return {
            "target": target,
            "filepath": filepath,
            "counts": (len(pre), len(post)),
            "elapsed": elapsed,
        }


async def main() -> None:
    args = sys.argv[1:]

    if "--list" in args:
        print("\n可用的 target：")
        for name, cfg in TARGETS.items():
            print(f"  · {name:<12} {cfg['base_url']}")
        print()
        return

    if args:
        targets = {t: TARGETS[t] for t in args if t in TARGETS}
        missing = [t for t in args if t not in TARGETS]
        if missing:
            print(f"⚠️  以下 target 不在 config.py 內：{', '.join(missing)}")
    else:
        targets = TARGETS

    if not targets:
        print("❌ 沒有可執行的 target，請確認 config.py 設定")
        return

    print(f"\n🚀 {len(targets)} 個 target | 並行上限：{MAX_CONCURRENT}\n")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [run_unit(t, cfg, semaphore) for t, cfg in targets.items()]

    t_start = time.perf_counter()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total = time.perf_counter() - t_start

    # ===== 結果摘要 =====
    print(f"\n{'=' * 66}\n  🏁 全部完成！總耗時 {_fmt_dur(total)}\n{'=' * 66}")
    print(f"  {'Target':<14}{'登入前':>8}{'登入後':>8}{'合計':>8}{'耗時':>10}")
    print(f"  {'-' * 62}")

    total_api = 0
    ok_units = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  ⚠️  某單元例外：{r}")
            continue
        ok_units.append(r)
        pre, post = r["counts"]
        total_api += pre + post
        print(f"  {r['target']:<14}{pre:>8}{post:>8}{pre + post:>8}"
              f"{_fmt_dur(r['elapsed']):>10}")

    print(f"  {'-' * 62}")
    print(f"  {len(ok_units)} 個 target | API 共 {total_api} 支 | 總耗時 {_fmt_dur(total)}")
    print(f"{'=' * 66}\n")

    for r in ok_units:
        print(f"  📄 {r['filepath']}")

    out = GENERATOR["output_dir"]
    print(f"\n💡 產出已落在：{out}")
    print("   這裡是交接點——把腳本交給測試框架 repo 執行：")
    print(f"   pytest {out} -v")
    print(f"   pytest {out} -v --html=report.html --self-contained-html\n")


if __name__ == "__main__":
    asyncio.run(main())
