# v2 更新模式影响矩阵

> 飞书文档 v2 CLI `docs +update --command …` 八种指令对批注/白板/图片/HTML 注释的影响。
> 来源：飞书评审工作法 §六实验矩阵（v1 验证）+ lark-cli 1.0.57 v2 能力实测 + **批注锚点机制研究成果**（block_id + 文本偏移）。
> `--api-version` 是 deprecated 兼容性标志，CLI 默认使用 v2，无需显式传。

## v2 八种指令影响矩阵

| 指令 (`--command`) | 批注(区域内) | 批注(区域外) | 白板(区域内) | 白板(区域外) | HTML 注释 | 批注 UI 可见 | 本 skill 用途 |
|------|------|------|------|------|------|------|------|
| `str_replace` | ⚠️ 见下 | ✅ 保留 | ⚠️ 见下 | ✅ 保留 | ❌ 删除 | ⚠️ 见下 | 🟢 策略 A 整章替换 / 🔴 策略 D 删前后 |
| `block_insert_after` | — | ✅ 保留 | ✅ 新增独立 | ✅ 保留 | ❌ 删除 | — | 插入新内容 / 🔴 策略 D 替代段落 |
| `block_replace` | ❌ 失效 | ✅ 保留 | ✅ **不动** | ✅ 保留 | ❌ 删除 | ❌ 不可见 | 🟡/🔴 策略 B/C 改文字 block（**仅当无批注落在文字上**） |
| `block_delete` | ❌ 删除 | ✅ 保留 | ❌ 删除该 block | ✅ 保留 | — | ❌ 不可见 | 删除废弃 block |
| `block_move_after` | ✅ 跟随 | ✅ 保留 | ✅ 跟随 | ✅ 保留 | — | ✅ 可见 | 重排 |
| `block_copy_insert_after` | — | ✅ 保留 | ✅ 复制 | ✅ 保留 | — | — | 复制 |
| `overwrite` | ✅ 保留(API) | ✅ 保留(API) | ❌ **全部删除** | ❌ **全部删除** | ❌ 删除 | ⚠️ **不可见** | ❌ **严禁**(规则 1，首次空文档除外) |
| `append` | — | ✅ 保留 | ✅ 新增 | ✅ 保留 | ❌ 删除 | — | 版本记录追加 |

**图例**：✅ 保留/不动 ｜ ❌ 删除/丢失 ｜ ⚠️ 有条件 ｜ — 不适用

---

## 关键结论

### 1. `str_replace` 对批注的影响取决于是否改动批注文字本身

飞书评注使用 **block_id + 文本内字符偏移** 双重锚定。`str_replace` 只删除批注文字前后内容、保留批注文字不动时，block ID 和偏移都保留，批注 UI 可见；一旦 `str_replace` 的 pattern/content 整体替换了包含批注文字的段落，文本偏移失效，API 数据仍在但 UI 不可见。策略 D 即利用这一特性安全更新带批注段落。

### 2. `block_replace` 会改变 block ID，导致批注锚点失效

`block_replace` 对文字 block 执行替换后，该 block 获得新 ID，原批注的 `content_anchor_id` 指向旧 ID，UI 不可见。因此策略 B/C 仅适用于**文字 block 上没有批注**的场景；若批注落在待修改文字上，必须升级/降级为策略 D（保留原文 + `block_insert_after`）。

### 3. `block_insert_after` 是新增 block，不影响已有批注

策略 D 用 `block_insert_after` 在前一 block 后插入替代段落，不动批注原文 block，因此不破坏批注锚点。限制：无 `block_insert_before`，需找到前一 block；且不能对批注段落使用 markdown `>` 引文格式（会触发 blockquote 转换，block ID 变）。

### 4. `block_replace` 是 v2 核心能力（策略 B/C 的基础）

- **v1 时代**（工作法 §8.3，2026-06-04）：`docs +update --mode block_replace` 不存在，只能 `lark-cli api PATCH` 原始调用。
- **v2 现在**（lark-cli 1.0.57）：`docs +update --command block_replace --block-id <id> --content <xml>` 是一等命令。
- **意义**：工作法 §9 升级清单 #5 已达成，策略 B/C 现在可执行。

### 5. `overwrite` 仍严禁（规则 1，v1/v2 一致）

工作法 §六 + 实验 #7（2026-06-07）反复验证：`overwrite` 后 API 返回批注数据未删除，但批注锚定的原文被整体替换，**飞书 UI 中批注无法定位显示**。v2 的 `overwrite` 行为相同，仍严禁用于增量同步。唯一例外：首次空文档推送。

### 6. `str_replace` 的 v2 行为

- **XML 模式（默认）**：`--pattern` 只支持行内匹配，不跨 block。
- **Markdown 模式**：支持跨行 + `前缀...后缀` 省略号语法，可整段替换。策略 A 用此模式做整章替换；策略 D 用此模式只删除批注文字前后内容，不碰批注文字本身。

### 7. HTML 注释在所有模式下被删

`<!--feishu:...-->` 行在推送时会被飞书后端删除。留在内容里的注释行无意义。必须先 `clean_copy.py` 剥离这些行，只推送真实内容（白板占位符、图片 markdown）。

---

## Block ID 生命周期（写操作后能否复用旧 ID）

v2 文档明确：写操作后**不要默认复用**之前 fetch 到的 block ID。

| 操作 | 旧 ID 是否有效 |
|------|---------------|
| `overwrite` / `block_replace` / `block_delete` | ❌ 受影响旧 ID 失效，继续 block 级操作前重新 fetch |
| `block_insert_after` / `append` / `block_copy_insert_after` | ⚠️ 锚点/源 ID 通常保留，新内容是新 ID |
| `block_move_after` | ⚠️ 被移动 ID 通常保留，但位置/章节变化 |
| `str_replace` | ✅ 简单行内替换通常不改变 ID；跨行/大段替换后先重新 fetch |

**对策**：连续 block 级操作之间，重新 `docs +fetch --detail with-ids` 获取最新 ID。

---

## 实验记录（v1 验证，v2 行为一致部分）

> 以下实验在工作法 §8.4 记录，用 v1 验证。v2 对应行为（白板/图片的删除语义）保持一致。

### 实验 A：`replace_range`（v1）/ `str_replace` 整章（v2）对白板的影响
- 整章替换含白板的章节 → 旧白板被删除，新空白板自动创建（若有 `<whiteboard type="blank">` 占位符）
- 旧 token 永久失效，返回新 token
- **结论**：含白板章节不能整章替换，改用 `block_replace`（策略 B/C）

### 实验 B：片段替换对白板的影响
- 即使只替换一句文字，若操作波及白板 block → 白板被删除
- **结论**：含白板章节必须用 `block_replace` 精准定位文字 block

### 实验 C：Block 级 PATCH（v1）/ `block_replace`（v2）对白板的影响
- 用 block 级操作更新文字 block → ✅ 文字更新，白板 token 不变
- **结论**：`block_replace` 是含白板章节的安全更新方式（策略 B/C 基础）

### 实验 D：整章替换对图片的影响
- 图片不会被删除（数量不变），但 token 会变化
- **结论**：图片比白板安全，但仍建议 `block_replace` 精准更新

---

## 本 skill 的使用约定

| 场景 | 用哪个指令 |
|------|-----------|
| 纯文本章节变更且无批注落在修改文字上 | `str_replace`（Markdown 模式 + 省略号语法）— 策略 A |
| 带批注且需修改批注文字 | `str_replace` 删前后 + `block_insert_after` 插入替代段 — 策略 D |
| 含白板章节的文字变更且无批注落在文字上 | `block_replace`（逐个文字 block）— 策略 B/C |
| 同步后追加版本记录 | `append` — 工作法规则 3 |
| 首次空文档全量推送 | `overwrite`（唯一允许场景） |
| 删除废弃 block | `block_delete`（批量用逗号分隔） |

**永远不用**：`overwrite`（增量同步场景，规则 1）；`str_replace` / `block_replace` / `block_delete` / `overwrite` 更新带批注的文字（改用策略 D）。

---

## v1 降级方案

若 CLI 版本低于 1.0.57，v2 标志不可用，降级为 v1 模式：

| v2 指令 | v1 降级模式 | 限制 |
|--------|-----------|------|
| `str_replace` | `replace_range` / `replace_all` | 无 `--pattern`，用 `--selection-by-title`/`--selection-with-ellipsis` |
| `str_replace` 删前后 + `block_insert_after` | **不可执行** | v1 无 `block_insert_after`/`block_insert_before`，策略 D 不可降级 |
| `block_replace` | **无降级方案** | 策略 B/C 不可执行 |
| `block_delete` | `delete_range` | 无 block ID 精准定位 |
| `append` | `append` | 相同 |
| `overwrite` | `overwrite` | 相同 |

---

## 参考
- 工作法 §六 更新模式影响矩阵
- 工作法 §8.2 已验证可用的能力 / §8.4 关键实验记录
- [comment-preservation-strategy.md](comment-preservation-strategy.md) — 批注锚点机制与策略 D 详解
- [sync-strategy-matrix.md](sync-strategy-matrix.md) — 策略 A/B/C/D 选路与 v2 命令
- [known-limits.md](known-limits.md) — 仍受限于 CLI 的能力 + 升级清单
- 官方 lark-doc `references/lark-doc-update.md` — v2 八种指令速查表 + Block ID 生命周期