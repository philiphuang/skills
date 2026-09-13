# 策略 A/B/C/D 适用条件与流程

> 本地 markdown 变更章节 → 飞书推送的四档策略。依据：飞书评审工作法 §七、§8.5 + 批注保留策略研究成果。
> **本 skill 基于 v2 CLI 实际能力**（`lark-cli` 1.0.57+）。
> `--api-version` 是 deprecated 兼容性标志，CLI 默认使用 v2，无需显式传。

## 选路决策树

```
            git diff 识别的变更章节
                      │
        拉取批注列表，判断批注是否落在待修改文字上
                      │
        ┌─────────────┴─────────────┐
        │                           │
    有批注落在修改文字上           无批注 / 批注不在修改区
        │                           │
        │         在本地 .md 搜该章节内 <!--feishu:...--> 标记
        │                           │
        │        ┌────────┬─────────┬──────────┐
        │        │        │         │          │
        │     纯文本    有白板    有白板     纯文本
        │     无标记   source=   source=    无标记
        │                │      mermaid    manual
        │                │         │         │
        │                │         │         │
     🔴 策略 D      🟡 策略 B  🔴 策略 C  🟢 策略 A
  保留原文          block_replace  block_replace  str_replace
  +block_insert_after  文字 block  文字 block  整章替换
                    + 白板重建    白板零触碰

判定优先级：
1. 先检查批注落点。若批注落在待修改文字上 → **策略 D**（无论是否有白板/图片）。
2. 无批注风险时，再按 `<!--feishu:...-->` 标记分 A/B/C：
   - 无 `<!--feishu:...-->` 标记 → A
   - `source=mermaid` → B
   - `source=manual` → C

---

## 🟢 策略 A：文本章节替换

**适用**：章节内无任何 `<!--feishu:...-->` 标记（纯文字章节）。

**v2 命令**（`str_replace` + Markdown 模式 + 省略号语法）：

```bash
# 1. 生成章节 Clean Copy（删 feishu 标记行 + 剥离本地元数据）
python3 skills/md2feishu/scripts/clean_copy.py "$FILE" --section "## 章节标题" -o ./_section_clean.md

# 2. str_replace 整章：用 --pattern "标题...下一章" 省略号定位，整段替换
lark-cli docs +update --doc "$OBJ_TOKEN" --command str_replace \
  --doc-format markdown \
  --pattern "## 变更章节标题...## 下一个章节" \
  --content "$(cat ./_section_clean.md)" \
  --as user

# 3. 校验
lark-cli docs +fetch --doc "$OBJ_TOKEN" --detail with-ids
```

**省略号语法说明**：v2 Markdown 模式下 `--pattern` 支持 `前缀...后缀`，三个英文句点串联首尾，匹配从前缀到后缀的全部内容（含中间被省略部分），用 `--content` 整体替换。适合首尾特征明显的章节。

**风险**：零（无受保护元素，批注锚定在章节内文字上，UI 可见）。

---

## 🟡 策略 B：含白板（source=mermaid）

**适用**：章节含 `<!--feishu:whiteboard TOKEN … source=mermaid-->` 标记。白板由 mermaid 代码生成，可重建。

**核心思路**：文字用 `block_replace` 逐个更新（只动文字 block，跳过白板 block），白板用 `whiteboard +update` 按 mermaid 源重新生成。

**流程**：

```bash
# 1. fetch 章节内容 + block id（v2 局部读取，避免全量 fetch）
#    先 outline 拿标题 id，再 section 精读
lark-cli docs +fetch --doc "$OBJ_TOKEN" --scope outline --max-depth 3
lark-cli docs +fetch --doc "$OBJ_TOKEN" \
  --scope section --start-block-id <标题block_id> --detail with-ids

# 2. 对每个变更的文字 block（跳过白板 block），block_replace
lark-cli docs +update --doc "$OBJ_TOKEN" --command block_replace \
  --block-id "blkcn文字block_id" --content '<p>更新后的文字</p>' --as user

# 3. 如 mermaid 源码也变更，whiteboard +update 重建（委托 lark-whiteboard）
#    先从 fetch 结果取 <whiteboard token="...">，再：
lark-cli whiteboard +update --token "$BOARD_TOKEN" --dsl-file ./new.mmd
```

**风险**：低。文字 block 独立更新，白板 block 不受影响；mermaid 白板按源重建内容可控。

---

## 🔴 策略 C：含白板（source=manual）

**适用**：章节含 `<!--feishu:whiteboard TOKEN … source=manual-->` 标记。白板手工绘制，**无法重建**，必须零触碰。

**核心思路**：与 B 相同的 fetch + block_replace 流程，但**白板完全不处理**（manual 白板没有源，任何重建都会丢失手工内容）。

**流程**：

```bash
# 1. 同 B：fetch 章节 + block id
lark-cli docs +fetch --doc "$OBJ_TOKEN" \
  --scope section --start-block-id <标题block_id> --detail with-ids

# 2. 仅 block_replace 变更的文字 block，白板 block 零触碰
lark-cli docs +update --doc "$OBJ_TOKEN" --command block_replace \
  --block-id "blkcn文字block_id" --content '<p>更新后的文字</p>' --as user

# 3. 不调用 whiteboard +update（manual 白板无源可重建）
```

**风险**：低（白板零触碰），但**不能替换整个章节**（`str_replace`/章节级 `replace_range` 会删除白板）。

---

## 🔴 策略 D：带批注文字的章节替换（保留原文）

**适用**：章节内存在批注，且 git diff 显示要修改的文字正好包含批注所引用的文字（即批注落在待修改文字上）。

**核心思路**：飞书评注使用 **block_id + 文本内字符偏移** 双重锚定。任何直接替换/删除批注所在 block 的操作（`str_replace` 碰批注文字、`block_replace`、`block_delete`、`overwrite`）都会让偏移或 block ID 失效，导致批注在 UI 层不可见。因此必须**保留批注原文不动**，用 `str_replace` 只删除批注文字前后的内容，再用 `block_insert_after` 在前一 block 后插入替代段落。

**流程**：

```bash
# 1. 获取批注列表，确认被批注文字与 block
lark-cli drive +list-comments --token "$OBJ_TOKEN" --json > ./_comments.json

# 2. 删除批注文字之前的内容（pattern 只匹配批注文字前一段）
lark-cli docs +update --doc "$OBJ_TOKEN" --command str_replace \
  --pattern "批注文字前面的内容。" \
  --content "" \
  --as user

# 3. 删除批注文字之后的内容（pattern 只匹配批注文字后一段）
lark-cli docs +update --doc "$OBJ_TOKEN" --command str_replace \
  --pattern "批注文字后面的内容。" \
  --content "" \
  --as user

# 4. 在前一 block 后插入替代段落
lark-cli docs +update --doc "$OBJ_TOKEN" --command block_insert_after \
  --block-id "<前一block的ID>" \
  --content "<p>替代段落内容</p>" \
  --as user
```

**文档结构示意**：

```
## 文档标题
这是替代的新段落。              ← block_insert_after 插入，新 block
如果直接修改被批注的文字。        ← 批注原文，block ID 和偏移不变，批注可见
其他段落...
```

**限制**：
- 批注段落不能加 markdown `>` 引文格式（会触发 blockquote 转换，block ID 变）。
- 无 `block_insert_before`，必须找到批注文字所在 block 的前一个 block。
- 批注文字在段落中间时，前后都要有明确可匹配的 pattern。

**风险**：低（批注可见），但会保留原文段落，造成"旧段+新段"并存；需确保新段在前、旧段在后，符合阅读顺序。

---

## 策略对比总表

| 策略 | 文字更新方式 | 白板/图片处理 | 适用条件 | 风险 | v2 命令数 |
|------|-------------|--------------|----------|------|----------|
| 🟢 A | `str_replace` 整章(markdown 省略号) | 无需处理 | 无 `<!--feishu:...-->` 且无批注落在修改文字上 | 零 | 1 |
| 🔴 D | `str_replace` 删前后 + `block_insert_after` 插入替代段 | 保留原章节内所有白板/图片（不碰原 block） | 批注落在待修改文字上 | 低 | 3 |
| 🟡 B | `block_replace` 逐个文字 block | `whiteboard +update` 重建 | `source=mermaid` 且无批注落在修改文字上 | 低 | N+1 |
| 🔴 C | `block_replace` 逐个文字 block | **零触碰**，白板 token 不变 | `source=manual` 且无批注落在修改文字上 | 低 | N |

**严禁**：
- ❌ `overwrite`（工作法规则 1，批注锚定文本整体替换后 UI 不可见）
- ❌ 对含批注且要修改批注文字的章节用策略 A/B/C 的 `str_replace` / `block_replace`（会丢批注）
- ❌ 对含白板章节用策略 A 的整章 `str_replace`（会删除白板）

---

## v1 降级方案（当 v2 不可用时）

若 CLI 版本低于 1.0.57，v2 标志不可用，可降级为 v1 模式：

| 策略 | v2 命令 | v1 降级命令 |
|------|---------|------------|
| 🟢 A | `str_replace --pattern "前缀...后缀"` | `replace_range --selection-by-title "## 标题"` |
| 🔴 D | `str_replace` 删前后 + `block_insert_after` | **不可执行**（v1 无 `block_insert_after`/`block_insert_before`） |
| 🟡 B | `block_replace` + `whiteboard +update` | `replace_range` 整章 + `<whiteboard type="blank">` 占位符重建（旧白板 token 失效） |
| 🔴 C | `block_replace` 零触碰 | **不可执行**（v1 无 block 级精准更新） |

---

## 参考
- 工作法 §七 安全更新策略
- 工作法 §8.5 基于当前能力的策略矩阵
- [comment-preservation-strategy.md](comment-preservation-strategy.md) — 批注锚点机制与保留策略
- [update-mode-impact.md](update-mode-impact.md) — v2 八种指令影响矩阵
- [known-limits.md](known-limits.md) — 仍受限于 CLI 的能力 + 升级清单
- 官方 lark-doc `references/lark-doc-update.md` — v2 八种指令详情
