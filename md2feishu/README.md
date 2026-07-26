# md2feishu — 飞书文档发布 Skill

把本地 markdown 变更**增量**同步到飞书 wiki 文档，保留批注、白板、图片。

飞书评审双向闭环的**发布半边**（本地 → 飞书）。获取方向（飞书 → 本地）由 [`/fei2md`](https://github.com/philiphuang/skills-factory/tree/main/products/fei2md) 负责。

## 它解决什么

飞书评审工作法（950 行实战文档）的"发布"方向有四个核心难点：
1. **用错更新模式会丢数据** — `overwrite` 让批注 UI 不可见，整章替换删白板
2. **章节提取越界 bug** — 终止条件只匹配同级标题，遇更高级标题会越界（实验 E 反复踩坑）
3. **推送前必须剥离本地元数据** — front matter / 批注快照 / h1 污染飞书正文
4. **"ok:true" ≠ 真的成功** — 必须重新 fetch 校验批注/白板/图片数量不减少

本 skill 把这些散落在 `sed`/`python3 -c` 一行命令里的逻辑，封装成正式、可测的 Python 脚本 + 官方技能编排。

## 架构：编排官方技能 + 自有领域逻辑

不自己调用 lark-cli，而是委托官方 `lark-*` 技能做 I/O，自己只做官方不覆盖的领域逻辑（与 fei2md 一致）：

```
git diff 章节 ──► extract_section.py ──► 选策略 A/B/C
                                               │
                     preprocess.py（mermaid校验+SVG转换）◄─┘
                                               │
                     clean_copy.py（剥离+清洗）◄─┘
                                               │
                     委托官方 lark-doc v2 推送 ◄─┘（str_replace / block_replace）
                                               │
                     SVG 后处理（whiteboard-cli 渲染）◄─┘
                                               │
                     verify_sync.py 校验 ◄──── 重新 fetch + comments list
```

## 脚本用法

| 脚本 | 命令 | 作用 |
|------|------|------|
| `strip_metadata.py` | `python3 scripts/strip_metadata.py strip <file.md>` | 剥离本地元数据（5 类） |
| | `python3 scripts/strip_metadata.py read-token <file.md>` | 读 feishu-doc wiki token |
| `preprocess.py` | `python3 scripts/preprocess.py <file.md>` | GH12 预处理：mermaid 校验 + SVG→白板转换 |
| | `python3 scripts/preprocess.py <file.md> --mapping-out map.json --warnings-out warn.json` | 输出 SVG 映射表和告警 |
| `extract_section.py` | `python3 scripts/extract_section.py --file <md> --title '## 章节'` | 提取章节（遇 ≥ 当前层级标题停止） |
| `clean_copy.py` | `python3 scripts/clean_copy.py <file.md>` | 生成 Clean Copy（删 feishu 标记行） |
| | `python3 scripts/clean_copy.py <file.md> --section '### 2.1'` | 章节级 Clean Copy（--section 须带 `#` 前缀） |
| `verify_sync.py` | `python3 scripts/verify_sync.py --before b.json --after a.json` | 同步后校验（批注/白板/图片/章节） |

> **JSON 快照来源**：`--before`/`--after` 需先用官方技能导出：
> - 文档内容：`lark-cli docs +fetch --doc <token> --doc-format markdown`
> - 批注数：`lark-cli drive comments list --doc-token <token>`
> - 合并为 `{"doc": "<markdown>", "comments_count": N}` 后喂给本脚本

## 策略 A/B/C/D

| 策略 | 适用 | v2 CLI 命令 | 风险 |
|------|------|-------------|------|
| 🟢 A | 纯文本章节（无 `<!--feishu:...-->` 标记，且批注未落在修改文字上） | `str_replace` 整章（Markdown 省略号） | 零 |
| 🔴 D | 批注落在待修改文字上 | `str_replace` 删前后 + `block_insert_after` 插入替代段 | 低 |
| 🟡 B | 含白板（`source=mermaid`，可重建，且批注未落在修改文字上） | `block_replace` 改文字 block + `whiteboard +update` 重建 | 低 |
| 🔴 C | 含白板（`source=manual`，不可重建，且批注未落在修改文字上） | `block_replace` 改文字 block，白板零触碰 | 低 |

> **v2 CLI 要求**：`lark-cli` 需 ≥ 1.0.57。`--api-version` 是 deprecated 兼容性标志，默认 v2，无需显式传。若 CLI 版本低于 1.0.57，策略 B/C/D 不可执行（v1 无 `block_replace` / `block_insert_after`），策略 A 降级为 `replace_range --selection-by-title`。详见 [references/known-limits.md](references/known-limits.md)。

## 四条强制规则（禁止违反）

1. **严禁 `overwrite`**（批注 UI 不可见；首次空文档除外）
2. **推送前剥离本地元数据**（front matter / comments 块 / h1 等）
3. **同步后追加 Git Commit 哈希**到飞书文档末尾
4. **多应用切换**用 `lark-cli config init`

## 测试

```bash
python3 -m pytest skills/md2feishu/tests/    # 60 项全绿
```

覆盖：实验 E 回归（H3→H2 不越界）、H2/H3/H4/H5 边界、Clean Copy 剥离/保留、verify_sync 通过/失败检测。

## 文档

- [SKILL.md](SKILL.md) — 技能本体（七步流程 + 强制规则）
- [设计文档](https://github.com/philiphuang/skills-factory/blob/main/src/md2feishu/DESIGN.md) — 完整设计
- [策略 A/B/C/D 矩阵](references/sync-strategy-matrix.md)
- [v2 更新模式影响矩阵](references/update-mode-impact.md)
- [批注保留策略](references/comment-preservation-strategy.md) — 批注锚点机制与策略 D
- [Mermaid 支持类型](references/mermaid-supported-types.json)
- [已知限制 + 升级清单](references/known-limits.md)
- 工作法全文：`docs/工作法/飞书评审/飞书评审工作法.md`

## 姊妹 skill

- [`/fei2md`](https://github.com/philiphuang/skills-factory/tree/main/products/fei2md) — 飞书 → 本地（获取方向）
- 两者通过同一份本地 markdown（front matter + 内联标记）解耦，构成双向闭环
