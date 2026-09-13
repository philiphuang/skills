# md2feishu 工作流参考

> 增量同步**七步**流程的完整命令参考。
> SKILL.md 仅包含流程摘要和选路逻辑，本文档提供逐步骤的可执行命令。

---

## Step 0：前置依赖检查

```bash
# 官方技能已安装（lark-doc v2 / lark-wiki / lark-drive / lark-shared）
npx skills add larksuite/cli -s lark-doc -s lark-wiki -s lark-drive -s lark-shared -y

# lark-cli 已登录且版本 >= 1.0.57
lark-cli auth login --domain docs,drive,wiki --recommend
lark-cli --version
```

---

## Step 1：读 front matter（无绑定时自动创建飞书文档）

```bash
# 尝试读已有绑定
WIKI_TOKEN=$(python3 skills/md2feishu/scripts/strip_metadata.py read-token "$FILE_PATH" 2>/dev/null || echo "")
LAST_COMMIT=$(python3 -c "
import yaml,sys
f=open('$FILE_PATH'); c=f.read(); f.close()
d=c.split('---')[1]
print(yaml.safe_load(d).get('sync',{}).get('last_commit',''))
" 2>/dev/null || echo "")

# 无绑定时自动创建飞书文档并写入 front matter
if [ -z "$WIKI_TOKEN" ]; then
  DOC_TITLE=$(grep -m1 '^# ' "$FILE_PATH" | sed 's/^# //')
  CREATE_RESULT=$(lark-cli docs +create --doc-format markdown \
    --content "# ${DOC_TITLE}" --format json --as user)
  WIKI_TOKEN=$(echo "$CREATE_RESULT" | jq -r '.data.document.document_id')
  WIKI_URL=$(echo "$CREATE_RESULT" | jq -r '.data.document.url')
  python3 - "$FILE_PATH" "$WIKI_TOKEN" "$WIKI_URL" "$DOC_TITLE" << 'PYEOF'
import sys
path, token, url, title = sys.argv[1:]
with open(path) as f:
    content = f.read()
parts = content.split("---", 2)
new_fm = f"""feishu-doc: {token}
feishu-title: "{title}"
feishu-url: {url}
sync:
  last_commit: ""
  last_synced_at: ""
"""
new_content = f"---\n{parts[1]}---\n{new_fm}---\n{parts[2].lstrip()}"
with open(path, "w") as f:
    f.write(new_content)
PYEOF
  echo "✅ 已创建飞书文档并绑定：$WIKI_URL"
fi
```

`LAST_COMMIT` 为空 → 视为首次推送，需用户确认是否全量。

---

## Step 2：git diff 识别变更章节

```bash
if [ -z "$LAST_COMMIT" ]; then
  echo "首次推送，全部章节都需同步"
else
  git diff --name-only "$LAST_COMMIT..HEAD" -- "$FILE_PATH"
  git diff "$LAST_COMMIT..HEAD" -- "$FILE_PATH"
fi

# 对每个变更章节提取内容
python3 skills/md2feishu/scripts/extract_section.py --file "$FILE_PATH" --title '## 变更章节'
```

> ⚠️ **章节提取终止条件**：必须遇任意 ≥ 当前层级的标题停止（修工作法实验 E 越界 bug）。
> `extract_section.py` 已正确实现。详见 [sync-strategy-matrix.md](sync-strategy-matrix.md)。

---

## Step 3：拉取批注列表，判断批注落点

在 Step 2 提取变更章节后、Step 4 选策略前，必须先获取批注列表：

```bash
# 1. 获取飞书文档 obj_token（若已有可复用）
OBJ_TOKEN=$(lark-cli drive +inspect --url "https://xxx.feishu.cn/wiki/$WIKI_TOKEN" \
  --format json | jq -r '.data.token')

# 2. 拉取批注列表（含 quote、content_anchor_id、is_whole、reply_list）
lark-cli drive +list-comments --token "$OBJ_TOKEN" --json > ./_comments.json

# 3. 解析批注落点：被批注文字（quote）与 Step 2 提取的变更章节内容交叉匹配，
#    判断是否有批注落在待修改文字上。可用章节旧文本（或 diff 删除部分）提高精度。
python3 skills/md2feishu/scripts/match_comments.py \
  --comments ./_comments.json \
  --section ./_section_old.md \
  --out ./_comment_hits.json
```

- `_comment_hits.json` 非空 → 该章节触发 **🔴 策略 D**（保留原文 + `block_insert_after`）。
- `_comment_hits.json` 为空 → 按原有 A/B/C 路径继续（无批注风险）。

> ⚠️ 批注判断必须基于 **文本内容匹配**（`quote` 字段），不能仅靠 block_id 是否落在变更区域内。

---

## Step 4：交叉判断，选策略

对每个变更章节，先检查 Step 3 的批注命中结果，再在提取的章节内容里搜 `<!--feishu:...-->` 标记：

| 章节含什么 | 批注是否落在修改文字上 | 策略 | 命令 |
|-----------|----------------------|------|------|
| 有批注命中 | 是 | 🔴 D | `str_replace` 删前后 + `block_insert_after` 插入替代段 |
| 无标记（纯文本） | 否 | 🟢 A | `str_replace` 整章 |
| `source=mermaid` 白板 | 否 | 🟡 B | `block_replace` 逐个文字 block + `whiteboard +update` |
| `source=manual` 白板 | 否 | 🔴 C | `block_replace` 零触碰白板 |

完整策略矩阵见 [sync-strategy-matrix.md](sync-strategy-matrix.md)。

---

## Step 5：预处理 → Clean Copy → 推送

```bash
# 预处理（mermaid 校验 + SVG 转换）
python3 skills/md2feishu/scripts/preprocess.py "$FILE_PATH" \
  --mapping-out ./_svg_mapping.json \
  --warnings-out ./_warnings.json \
  -o ./_preprocessed.md
if [ -s ./_warnings.json ]; then
  jq -r '.[]' ./_warnings.json
fi

# Clean Copy
python3 skills/md2feishu/scripts/clean_copy.py ./_preprocessed.md -o ./_clean.md

# 推送前转换 wiki token → obj_token
OBJ_TOKEN=$(lark-cli drive +inspect --url "https://xxx.feishu.cn/wiki/$WIKI_TOKEN" \
  --format json | jq -r '.data.token')

# 🟢 策略 A：纯文本章节
lark-cli docs +update --doc "$OBJ_TOKEN" --command str_replace \
  --doc-format markdown \
  --pattern "## 变更章节...## 下一章节" \
  --content "$(cat ./_section_clean.md)" \
  --as user

# 🔴 策略 D：带批注文字章节（保留原文 + 插入替代段落）
# 前置：已从 Step 3 拿到 comment_hits，明确被批注文字与前一 block ID
# 步骤 1：删除批注文字之前的内容
lark-cli docs +update --doc "$OBJ_TOKEN" --command str_replace \
  --pattern "批注文字前面的内容。" \
  --content "" \
  --as user
# 步骤 2：删除批注文字之后的内容
lark-cli docs +update --doc "$OBJ_TOKEN" --command str_replace \
  --pattern "批注文字后面的内容。" \
  --content "" \
  --as user
# 步骤 3：在前一 block 后插入替代段落
lark-cli docs +update --doc "$OBJ_TOKEN" --command block_insert_after \
  --block-id "<前一block的ID>" \
  --content "<p>替代段落内容</p>" \
  --as user

# 🟡 策略 B：含 mermaid
lark-cli docs +fetch --doc "$OBJ_TOKEN" --scope outline --max-depth 3
lark-cli docs +fetch --doc "$OBJ_TOKEN" \
  --scope section --start-block-id <标题block_id> --detail with-ids
lark-cli docs +update --doc "$OBJ_TOKEN" --command block_replace \
  --block-id "blkcn文字block_id" --content '<p>更新后的文字</p>' --as user
lark-cli whiteboard +update --token "$BOARD_TOKEN" --dsl-file ./new.mmd

# 🔴 策略 C：含 manual 白板（零触碰白板）
lark-cli docs +fetch --doc "$OBJ_TOKEN" \
  --scope section --start-block-id <标题block_id> --detail with-ids
lark-cli docs +update --doc "$OBJ_TOKEN" --command block_replace \
  --block-id "blkcn文字block_id" --content '<p>更新后的文字</p>' --as user
# ❌ 不调 whiteboard +update
```

> `lark-cli` 需 ≥ 1.0.57。`--api-version` 是 deprecated 兼容性标志，默认 v2。

---

## Step 6：SVG 后处理 → 状态回写

```bash
# SVG 白板渲染（映射表非空时执行）
for i in $(seq 0 $(($(jq length ./_svg_mapping.json) - 1))); do
  SVG_PATH=$(jq -r ".[$i].svg_path" ./_svg_mapping.json)
  BOARD_TOKEN=$(echo "$DOC_RESPONSE" | jq -r ".data.document.new_blocks[$i].block_token")
  npx -y @larksuite/whiteboard-cli@^0.2.11 \
    -i "$SVG_PATH" --from svg --to openapi --format json 2>/dev/null | \
  lark-cli whiteboard +update \
    --whiteboard-token "$BOARD_TOKEN" \
    --input_format raw --source - --overwrite --as user
  if [ $? -ne 0 ]; then
    echo "⚠️ SVG 白板渲染失败：$SVG_PATH" >&2
  fi
done

# 状态回写
lark-cli docs +update --doc "$OBJ_TOKEN" --command append \
  --markdown "$(printf '### v%s\n\n更新摘要：\n\n**Git Commit**：%s' "$VERSION" "$COMMIT_HASH")" \
  --as user
```

---

## Step 7：自动校验

```bash
# 同步前快照（在 Step 1 后、Step 5 前）
lark-cli docs +fetch --doc "$OBJ_TOKEN" --format json > ./_before.json
COMMENTS_BEFORE=$(lark-cli drive file.comments list \
  --params '{"file_token":"'"$OBJ_TOKEN"'","file_type":"docx"}' \
  --as user --format json | jq '.data.items | length')
jq --argjson c "$COMMENTS_BEFORE" '. + {comments_count: $c}' ./_before.json > ./_before_full.json

# 同步后快照（Step 6 完成后）
# 同上生成 ./_after_full.json

# 比对
python3 skills/md2feishu/scripts/verify_sync.py --before ./_before_full.json --after ./_after_full.json
# 退出码 0 = 通过，1 = 有维度减少
```

校验表见 [DESIGN.md](https://github.com/philiphuang/skills-factory/blob/main/src/md2feishu/DESIGN.md) §3。

---

## 参考

- [SKILL.md](../SKILL.md) — 技能本体与强制规则
- [策略 A/B/C/D 矩阵](sync-strategy-matrix.md) — 选路与 v2 命令
- [v2 更新模式影响矩阵](update-mode-impact.md) — 八种指令对批注/白板/图片的影响
- [批注保留策略](comment-preservation-strategy.md) — 批注锚点机制与策略 D 详解
- [已知限制](known-limits.md) — 仍受限于 CLI 的能力 + 升级清单
- [Mermaid 支持类型](mermaid-supported-types.json) — 9 种 + 降级规则
- [设计文档](https://github.com/philiphuang/skills-factory/blob/main/src/md2feishu/DESIGN.md) — 完整架构设计
