---
name: md2feishu
description: 把本地 markdown 变更增量同步到飞书 wiki 文档，保留批注、白板、图片。读本地文件的 git diff 识别变更章节，按是否含受保护元素选策略 A/B/C/D（纯文本章节用 str_replace；含批注且需改批注文字时用 block_insert_after 保留原文；含白板章节用 block_replace 精准改文字 block），推送前剥离本地元数据生成 Clean Copy，推送后校验批注/白板/图片/章节数量不减少。当用户想"发布 markdown 到飞书""同步本地变更到飞书文档""把评审修改推回飞书""增量更新飞书文档不丢批注"时使用此 skill。不负责从飞书拉取（走 fei2md skill）、不负责批注拉取/分类/关闭（走 fei2md）、不负责飞书文档内容读取（走官方 lark-doc 技能）。
---

# md2feishu — 飞书文档发布

把本地 markdown 变更**增量**同步到飞书 wiki，保留批注、白板、图片。
飞书评审双向闭环的**发布半边**。获取方向（飞书 → 本地）由 `/fei2md` 负责。

## 架构：编排官方技能 + 自有领域逻辑

| 能力 | 由谁负责 |
|------|---------|
| 文档 fetch / update / append | **官方 `lark-doc`** v2 |
| wiki → doc token 转换 | **官方 `lark-wiki` / `lark-drive +inspect`** |
| 批注数量校验 | **官方 `lark-drive`** comments list |
| 白板重建（mermaid 源） | **官方 `lark-whiteboard`** |
| git diff 章节定位 | **本 skill** `extract_section.py` |
| mermaid 校验 + SVG 预处理 | **本 skill** `preprocess.py` |
| Clean Copy (strip + 清洗) | **本 skill** `clean_copy.py` + `strip_metadata.py` |
| 批注锚点识别（block_id + 文本偏移） | **本 skill** `match_comments.py` + `lark-drive +list-comments` |
| 策略 A/B/C/D 选路 | **本 skill** 按 `<!--feishu:...-->` 标记 + 批注落点 |
| 同步后校验 | **本 skill** `verify_sync.py` |

前置依赖：`.agents/skills/` 需安装官方技能：
```bash
npx skills add larksuite/cli -s lark-doc -s lark-wiki -s lark-drive -s lark-shared -y
```

## 强制规则

1. **严禁 `overwrite`** — 批注锚定文本整体替换后 UI 不可见。唯一例外：首次空文档推送。
2. **带批注文字严禁直接替换** — 飞书评注用 `block_id + 文本偏移` 双重锚定。`str_replace` 动了批注文字会导致偏移失效、UI 不可见；必须保留批注原文独立成段，用 `block_insert_after` 在前一 block 后插入替代段落。详见 [references/comment-preservation-strategy.md](references/comment-preservation-strategy.md)。
3. **推送前必须剥离本地元数据** — front matter / comments 块 / h1 / blockquote 不进飞书正文。
3. **同步后追加 Git Commit 哈希** — 飞书文档末尾追加 commit 短哈希。
4. **多应用切换** — `lark-cli config init --app-id <新> --app-secret-stdin --brand feishu`。

## 前置条件

- `lark-cli` v2+ 已安装并 OAuth 登录：`lark-cli auth login --domain docs,drive,wiki --recommend`
- 本地 markdown 已绑定飞书文档（front matter 含 `feishu-doc`，见 fei2md [front-matter-schema.md](https://github.com/philiphuang/skills-factory/blob/main/products/fei2md/references/front-matter-schema.md)）
- 文件已 `git commit`（增量同步依赖 git diff）

## 流程概要

| 步骤 | 动作 | 详情 |
|------|------|------|
| 1 | 读 front matter | 取 `feishu-doc` + `sync.last_commit`；无绑定时自动创建飞书文档 |
| 2 | git diff 识别变更 + 拉取批注 | `git diff <last_commit>..HEAD` → 提取变更章节；`lark-drive +list-comments` 取批注落点 |
| 3 | 交叉判断选策略 | 章节含 `<!--feishu:...-->` 标记？批注落在待修改文字上？→ A/B/C/D |
| 4 | 预处理 + Clean Copy + 推送 | `preprocess.py` → `clean_copy.py` → `lark-doc +update` |
| 5 | SVG 后处理 + 状态回写 | `whiteboard-cli` 渲染 SVG → 更新 front matter + 追加版本记录 |
| 6 | 自动校验 | `verify_sync.py` 对比同步前后批注/白板/图片/章节数量 |

完整命令参考见 [`references/workflow.md`](references/workflow.md)。

## 脚本说明

| 脚本 | 职责 |
|------|------|
| `strip_metadata.py` | 剥离 5 类本地元数据（与 fei2md 行为一致） |
| `preprocess.py` | mermaid 类型校验（9 种支持、不支持降级 code） + SVG 引用→空白白板占位符 |
| `extract_section.py` | 按"遇 ≥ 当前层级标题停止"提取章节（修实验 E bug） |
| `clean_copy.py` | 删 feishu 标记行，保留 whiteboard 占位符和图片 |
| `match_comments.py` | 读 `lark-drive +list-comments` 结果，与变更章节文本交叉匹配，输出命中批注 |
| `verify_sync.py` | 对比同步前后快照，校验维度不减少 |

**安全声明**：本 skill 处理 wiki token / commit 哈希等标识符，不处理密钥或 OAuth token（由 `lark-cli auth` 管理）。脚本纯逻辑，不调 lark-cli，所有 I/O 由本 skill 编排官方技能完成。

## 错误处理

| 场景 | 处理 |
|------|------|
| 文件不存在 / 无 front matter | 提示检查路径或添加绑定 |
| 无 `sync.last_commit` | 视为首次推送，提示用户确认全量 |
| git 无变更 | "✅ 本地与飞书已同步，无变更" |
| mermaid 类型不支持 | 告警并降级为代码块（preprocess 自动处理） |
| SVG 不存在 / 渲染失败 | 告警并跳过，白板留空 |
| 推送后批注不可见但 API 返回存在 | 说明批注锚点偏移失效；回滚该章节，改用 block_insert_after 保留原文策略 |
| 推送后白板/批注数减少 | 警告，提示检查策略选择（可能误用 overwrite 或 block_replace 到带批注 block） |
| lark-cli 未登录 / 非 v2 | 提示 `lark-cli update` + `lark-cli auth login` |

## 测试

```bash
# 全部单元测试
python3 -m pytest products/md2feishu/tests/

# GH12 预处理单独验证
python3 -m pytest products/md2feishu/tests/test_preprocess.py -v

# 批注落点匹配单独验证
python3 -m pytest products/md2feishu/tests/test_match_comments.py -v
```

## 参考

- [工作流详细命令](references/workflow.md) — 六步可执行命令
- [策略 A/B/C/D 矩阵](references/sync-strategy-matrix.md) — 选路 + v2 命令
- [v2 更新模式影响矩阵](references/update-mode-impact.md) — 八种指令对批注/白板/图片的影响
- [批注保留策略](references/comment-preservation-strategy.md) — 批注锚点机制与安全策略
- [已知限制](references/known-limits.md) — 仍受限能力 + lark-cli 升级检查
- [Mermaid 支持类型](references/mermaid-supported-types.json) — 9 种 + 降级规则
- [设计文档](https://github.com/philiphuang/skills-factory/blob/main/src/md2feishu/DESIGN.md) — 完整架构设计
