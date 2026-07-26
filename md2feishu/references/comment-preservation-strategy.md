# 飞书文档批注保留策略

> 研究成果来源：`/Users/philiphuang/all/personal/projects/sop/docs/agents/feishu-comment-preservation-strategy.md`
> 本 skill 在增量同步章节时，必须遵守以下策略，确保已存在的批注（评论）在 UI 层不丢失。

## 问题背景

飞书文档更新时，如何保证已存在的批注（评论）不丢失？

## 现有能力

| 能力 | Skill | 命令 |
|------|-------|------|
| 获取批注列表 | lark-drive | `lark-cli drive +list-comments --token <url>` |
| 添加批注 | lark-drive | `lark-cli drive +add-comment --doc <url> --selection-with-ellipsis "文字" --content '[...]'` |
| 更新文档内容 | lark-doc | `lark-cli docs +update --doc <url> --command str_replace ...` |
| 更新文档内容 | lark-doc | `lark-cli docs +update --doc <url> --command block_insert_after ...` |

## API 关键信息

- **端点**：`GET /open-apis/drive/v1/files/:file_token/comments?file_type=docx`
- **权限**：`docs:document.comment:read`
- **频率限制**：1000 次/分钟
- **区分全文/局部**：`is_whole=true`（全文评论）vs `is_whole=false`（局部批注）
- **返回字段**：`comment_id`, `user_id`, `quote`（被引用文字）, `reply_list`, `is_solved`, `content_anchor_id`（锚点 block ID）

## 核心发现：评论锚点机制

飞书批注使用 **block_id + 文本内字符偏移** 双重锚定。因此：

| 操作 | Block ID | 文本偏移 | UI 可见 |
|------|----------|----------|---------|
| `block_delete` / `block_replace` | 变 | 失效 | ❌ |
| `overwrite` | 全变 | 全失效 | ❌ |
| `str_replace` 替换了批注文字本身 | 保留 | **偏移失效** | ❌ |
| `str_replace` 只删批注文字前后内容 | 保留 | **保留** | ✅ |
| `block_insert_after` | 不影响 | 不影响 | ✅ |

## 安全策略分级

| 操作 | 安全等级 | 说明 |
|------|---------|------|
| `block_insert_after` | ✅ 安全 | 插入新 block，不动已有 |
| `str_replace`（不碰批注文字） | ✅ 安全 | 只删前后，偏移不变 |
| `str_replace`（动人批注文字） | ❌ 危险 | API 层评论在，UI 层不可见 |
| `block_replace` | ❌ 危险 | block ID 变，锚点失效 |
| `block_delete` | ❌ 危险 | 删除 block，评论丢失 |
| `overwrite` | ❌ 危险 | 全量重写，评论全部丢失 |
| markdown `>` 引文格式 | ❌ 危险 | 触发 blockquote 转换，block ID 变 |

## 方案 A：保留原文独立成段（经验证可行）

当批注落在需要修改的文字上时，不能直接 str_replace 那段文字。改为：只删除批注前后的无关内容，保留批注文字不动。

### 操作步骤

```bash
# 前置：fetch 文档获取 block ID 和内容
lark-cli docs +fetch --doc "<url>" --detail with-ids --format json

# 前置：获取批注列表，确定被批注的文字所在 block 和具体内容
lark-cli drive +list-comments --token "<url>" --json

# 步骤 1：删除批注文字之前的内容
lark-cli docs +update --doc "<url>" --command str_replace \
  --pattern "批注文字前面的内容。" \
  --content ""

# 步骤 2：删除批注文字之后的内容
lark-cli docs +update --doc "<url>" --command str_replace \
  --pattern "批注文字后面的内容。" \
  --content ""

# 步骤 3：在标题或前一 block 后插入替代段落
lark-cli docs +update --doc "<url>" --command block_insert_after \
  --block-id "<前一block的ID>" \
  --content "<p>替代段落内容</p>"
```

### 文档结构示意

```
## 文档标题
这是替代的新段落。              ← 新增替代内容，block_insert_after
如果直接修改被批注的文字。        ← 批注原文，block ID 和偏移不变，批注可见
其他段落...
```

### 限制

1. 批注段落无法加引文格式（`>` markdown 会触发 blockquote 转换，block ID 变）
2. 无 `block_insert_before` 命令，需用 `block_insert_after` 前一 block 变通
3. 如果批注文字在段落中间，前后都要有明确的 pattern 可匹配

## 实验记录

| 实验 | 策略 | 文档 | 结果 |
|------|------|------|------|
| v1 | markdown `>` str_replace 全段 | https://asppm.feishu.cn/docx/SyRzdVTcUo3s71xCIgJcnUE6nFf | ❌ block ID 变，UI 不可见 |
| v2 | XML 模式 str_replace 全段 | https://asppm.feishu.cn/docx/WKV8dJVXqo8Z4lxbG0UcRRMhn2g | ❌ block ID 保留但偏移失效，UI 不可见 |
| v3 | 只删前后，不动批注文字 | https://asppm.feishu.cn/docx/GYm3dG9Q5o6Kc8xQyy8cGfrbnZg | ✅ block ID 保留，偏移不变，UI 可见 |

## 建议的工作流约定

1. 更新文档前，先用 `drive +list-comments` 列出所有批注
2. 对于带批注的段落：
   - 用 str_replace 分别删除批注文字前后的内容（不碰批注文字本身）
   - 用 block_insert_after 在前一 block 后插入替代段落
3. 不带批注的段落，直接用 `str_replace` 修改
4. 永远不要用 `overwrite`、`block_replace`、`block_delete` 更新带批注的内容

## 与策略 A/B/C 的关系

- 本策略是 **策略 A 的 comment-aware 变体**，仅当纯文本章节中存在批注落在待修改文字上时触发。
- 含白板/图片的章节仍优先使用策略 B/C（`block_replace` 改文字 block，见 [sync-strategy-matrix.md](sync-strategy-matrix.md)）。
- 所有更新操作对批注的影响详细矩阵见 [update-mode-impact.md](update-mode-impact.md)。
