# 已知限制 + lark-cli 升级检查清单

> 本 skill 基于的能力边界。仍受限于 CLI 的能力 + lark-cli 升级后需重验的清单。
> 来源：飞书评审工作法 §九（升级检查清单）、§十（已知限制）。
> **当前 CLI 版本**：`lark-cli 1.0.57`（v2 标志已解锁）。
> `--api-version` 是 deprecated 兼容性标志，CLI 默认使用 v2，无需显式传。

## 当前已解锁（v2 CLI 1.0.57 实测）

| # | 能力 | 状态 | 验证命令 | 说明 |
|---|------|------|----------|------|
| 1 | `--command str_replace` | ✅ 可用 | `lark-cli docs +update --command str_replace --help` | 策略 A |
| 2 | `--command block_replace` + `--block-id` | ✅ 可用 | `lark-cli docs +update --command block_replace --block-id test --help` | 策略 B/C 基础 |
| 3 | `--doc-format markdown` + `--pattern` | ✅ 可用 | `lark-cli docs +update --doc-format markdown --pattern test --help` | 策略 A v2 写法 |
| 4 | `--scope` + `--detail with-ids` | ✅ 可用 | `lark-cli docs +fetch --scope outline --detail with-ids --help` | 局部读取 + block ID 获取 |
| 5 | `--command append` | ✅ 可用 | `lark-cli docs +update --command append --help` | 版本记录追加 |
| 6 | `docs +fetch`（基础 fetch） | ✅ 可用 | `lark-cli docs +fetch --doc TOKEN` | 返回文档 JSON/XML |
| 7 | `drive +list-comments` / `drive +add-comment` | ✅ 可用 | `lark-cli drive +list-comments --help` | 批注落点识别（策略 D 前置） |
| 8 | `--command block_insert_after` | ✅ 可用 | `lark-cli docs +update --command block_insert_after --help` | 策略 D 插入替代段落 |

## 仍受限于 CLI（未解锁）

| # | 能力 | 当前状态 | 验证命令 | 影响 |
|---|------|---------|----------|------|
| 9 | 白板 `+query --output_as raw` | ❌ | `lark-cli whiteboard +query --output_as raw` | 无法获取 manual 白板原始数据 |
| 10 | 白板 `+query --output_as code` | ❌ | `lark-cli whiteboard +query --output_as code` | 无法判断白板是否由代码生成 |
| 11 | whiteboard v1 API | ❌ HTTP 404 | `lark-cli api GET /open-apis/whiteboard/v1/...` | 白板 Open API 未开放 |

→ **策略 A/B/C/D 现在可执行**（#1-#8 已解锁）。
→ **v5 白板保护式 export→import 仍不做**（依赖 #9/#10/#11）。

---

## 关于 "v2" 的澄清

### 混淆来源

`lark-doc` skill（`.agents/skills/lark-doc/SKILL.md`）front matter 标注 `version: 2.0.0`，
并在文档中要求 `--api-version v2`。这导致以下混淆：

- **Skill 版本 2.0.0** = skill 描述符（文档规范）的版本
- **CLI 版本** = 实际二进制能力。最新 npm 发布为 `1.0.57`（2026-06-23），本机从 `1.0.0` 升级而来
- **API 版本** = 飞书后端 API 版本。CLI 作为封装层，其版本与后端 API 版本解耦

### 实测证据（1.0.57）

```bash
# CLI 版本
$ lark-cli --version
lark-cli version 1.0.57

# --api-version 是 deprecated 兼容性标志，默认 v2
$ lark-cli docs +update --help
Flags:
  --api-version string     deprecated compatibility flag; docs shortcuts always use v2
  --command string         str_replace|block_delete|block_insert_after|block_copy_insert_after|block_replace|block_move_after|overwrite|append
  --block-id string        target block ID(s) for block operations
  --doc-format string      xml|markdown
  --pattern string         str_replace match pattern
  --content string         replacement or inserted content

# +fetch 也支持 v2 标志
$ lark-cli docs +fetch --help
Flags:
  --scope string            full|outline|range|keyword|section
  --detail string           simple|with-ids|full
  --start-block-id string   range/section anchor block id
  --end-block-id string     range end block id
```

### 升级路径

CLI 升级需通过 npm：

```bash
npm install -g @larksuite/cli@latest
# 当前最新：1.0.57（2026-06-23 发布）
```

---

## 已知限制

### 1. v5 白板保护式 export→import 仍不可实现

即使 v2 `block_replace` 已解锁，manual 白板的保护式重建仍依赖白板导出能力：
- `whiteboard +query --output_as raw`（#8）未解锁
- `whiteboard +query --output_as code`（#9）未解锁
- whiteboard v1 API（#10）返回 404

**当前做法**：策略 C 用 `block_replace` 零触碰白板（不调用 whiteboard +update），
是最安全的做法，但非「保护式」（若文字 block 与白板的相对位置关系被破坏，白板可能漂移）。

**升级路径**：#8 或 #9 或 #10 解锁后，可实现 v5「replace 前 export 白板，后 import 还原」。

### 2. `overwrite` 后批注 API 可读但 UI 不可见（Bug）

工作法 §十、实验 #7（2026-06-07）：`overwrite` 后 `drive file.comments list` 仍返回批注数据，
但飞书 UI 中批注无法定位显示（锚定原文被整体替换）。v2 行为相同。

**对策**：规则 1 严禁 `overwrite`（首次空文档除外）。增量同步一律用 `str_replace`（策略 A）、`block_insert_after`（策略 D）或 `block_replace`（策略 B/C，仅当文字 block 无批注时）。

### 3. `block_replace` 对文字 block 上的批注会丢锚点

`block_replace` 替换文字 block 后，该 block 获得新 ID，原批注的 `content_anchor_id` 指向旧 ID，API 数据仍在但 UI 不可见。这与 `overwrite` 症状类似，只是范围更小。

**对策**：更新前先用 `drive +list-comments` 识别批注落点。若批注落在待修改文字上，必须改用策略 D（保留原文 + `block_insert_after`），不能对文字 block 用 `block_replace` 或整章 `str_replace`。

### 4. HTML 注释被后端删除

`<!--...-->` 在所有推送模式下会被飞书后端删除。留在内容里的 `<!--feishu:...-->` 标记行无意义。
**对策**：推送前用 `clean_copy.py` 剥离这些行，只保留真实元素（白板占位符、图片 markdown）。

### 5. 章节提取靠 source 标记判定白板类型

策略 B（mermaid）/C（manual）的分流依赖 `<!--feishu:whiteboard TOKEN 描述 source=mermaid|manual-->` 标记。
若白板标记缺失 `source` 字段，本 skill 默认按 **C（manual，零触碰）** 处理（保守策略，宁可不动白板）。

### 6. Mermaid 白板限制（GH12 实测）

| 能力 | 状态 | 说明 |
|------|------|------|
| mermaid ```` ```mermaid ```` 代码块 | ✅ 自动创建 + 渲染白板 | `lark-doc +create/+update` 一步完成 |
| mermaid 图类型校验 | ✅ `preprocess.py` 实现 | 9 种支持类型，不支持降级为 `<code>` |
| SVG → 白板 | ⚠️ 两步：`<whiteboard type="blank">` + `whiteboard-cli` | 需后处理 SVG 映射表 |
| SVG 不兼容特性（渐变/滤镜/mask） | ⚠️ 告警 | `whiteboard-cli` 会降级或报错 |
| `whiteboard-cli` 未安装 | ❌ SVG 白板失败 | 需 `npx @larksuite/whiteboard-cli` |

---

## lark-cli 升级检查清单

> 每次升级 `lark-cli` 后，逐项验证。全部通过后更新本清单的"状态"列。

| # | 检查项 | 1.0.0 状态 | 1.0.57 状态 | 验证命令 |
|---|--------|-----------|------------|----------|
| 1 | `lark-cli --version` 已升级 | 1.0.0 | ✅ 1.0.57 | `lark-cli --version` |
| 2 | `--command str_replace` 可用？ | ❌ | ✅ | `lark-cli docs +update --command str_replace --help` |
| 3 | `--command block_replace` 可用？ | ❌ | ✅ | `lark-cli docs +update --command block_replace --help` |
| 4 | `--block-id` 可用？ | ❌ | ✅ | `lark-cli docs +update --block-id test --help` |
| 5 | `--scope` / `--detail with-ids` 可用？ | ❌ | ✅ | `lark-cli docs +fetch --scope outline --help` |
| 6 | `--doc-format markdown` 可用？ | ❌ | ✅ | `lark-cli docs +fetch --doc-format markdown --help` |
| 7 | `--command block_insert_after` 可用？ | ❌ | ✅ | `lark-cli docs +update --command block_insert_after --help` |
| 8 | `drive +list-comments` 可用？ | ❌ | ✅ | `lark-cli drive +list-comments --help` |
| 9 | 白板 `+query --output_as raw` 可用？ | ❌ | ❌ | `lark-cli whiteboard +query --output_as raw` |
| 10 | 白板 `+query --output_as code` 可用？ | ❌ | ❌ | `lark-cli whiteboard +query --output_as code` |
| 11 | whiteboard v1 API 可访问？ | ❌ 404 | ❌ 404 | `lark-cli api GET /open-apis/whiteboard/v1/...` |
| 12 | `schema docx.*` 已注册？ | ❌ | ❌ | `lark-cli schema docx.document.block.patch` |
| 13 | `str_replace` 是否仍删区域内白板？ | ⚠️ 删 | ⚠️ 删 | 重复工作法实验 A |
| 14 | `block_replace` 是否真能零触碰白板？ | — 无此命令 | 待验证 | 重复工作法实验 C（v2 版） |
| 15 | `block_insert_after` 插入段落是否影响相邻批注？ | — 无此命令 | 待验证 | 验证策略 D 安全性 |

### 升级后策略升级路径

| 若检查项通过 | 策略变更 |
|--------------|----------|
| #2-#6（v2 核心标志可用） | 🟡 策略 B 可执行、🔴 策略 C 可执行（1.0.57 已达成） |
| #7-#8（`block_insert_after` + `list-comments` 可用） | 🔴 策略 D 可执行（保留原文 + 插入替代段落） |
| #9 或 #10 或 #11（白板导出可用） | 🔴 策略 C 升级为「保护式」：replace 前 export 白板，后 import 还原（v5） |
| #13（str_replace 不删白板） | 策略 A 可考虑用于含白板章节（但保守起见仍用 block_replace） |
| #14（验证 block_replace 零触碰） | 策略 B/C 的安全性从「文档声明」升级为「实测确认」 |
| #15（验证 block_insert_after 不影响相邻批注） | 策略 D 的安全性从「文档声明」升级为「实测确认」 |

---

## 参考
- 工作法 §九 CLI 能力基线与升级检查清单
- 工作法 §十 已知限制
- 工作法 §0.1 强制规则（规则 1 严禁 overwrite）
- [comment-preservation-strategy.md](comment-preservation-strategy.md) — 批注锚点机制与策略 D
- [sync-strategy-matrix.md](sync-strategy-matrix.md) — 策略 A/B/C/D（v2 版）
- [update-mode-impact.md](update-mode-impact.md) — v2 八种指令影响矩阵
- [mermaid-supported-types.json](mermaid-supported-types.json) — GH12 mermaid 支持类型清单
- 官方 lark-doc skill: `.agents/skills/lark-doc/SKILL.md`（v2.0.0 规范）
- 官方 lark-doc `references/lark-doc-update.md` — v2 命令速查
