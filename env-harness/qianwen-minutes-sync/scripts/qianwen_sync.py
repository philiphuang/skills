#!/usr/bin/env python3
"""qianwen_sync.py — 千问纪要同步管线入口（薄壳，实现在 qianwen_sync/ 包）。

用法：
    python3 qianwen_sync.py run [--dry-run]        # 拉取→分类→归档→报告
    python3 qianwen_sync.py finalize --answers a.json
规范：references/archive-spec.md、classification-spec.md、run-spec.md（PR #200）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qianwen_sync.run import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
