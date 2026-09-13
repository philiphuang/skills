# md2feishu 设计文档

> 飞书文档发布技能(`/md2feishu`)的设计文档。
> 对应 GitHub Issue #9。本文档是 skill 产物的设计依据,产物本体在 `skills/md2feishu/`。

---

## 1. 职责边界

`md2feishu` 是飞书评审双向闭环的**发布半边**(原工作法 `/review-sync` 方向):

```
本地 markdown ──git diff──► 变更章节
   (含 front matter /           │
    内联标记 / 批注快照)         ├── 无受保护元素 → 🟢 策略 A 整章替换
                                 ├── 含白板(mermaid) → 🟡 策略 B 文字 block 改 + 白板重建
                                 └── 含白板(manual) → 🔴 策略 C 仅改文字 block、白板零触碰
                                         │
   飞书 wiki 文档 ◄──push──  Clean Copy (剥离本地元数据 + feishu 标记行)
                                         │
   状态回写 → 校验 (批注数/白板数/图片数/章节结构 ≥ 同步前)
```

### 架构决策:编排官方技能 + 自有领域逻辑(与 fei2md 对齐)

本 skill **不自己调用 lark-cli 的文档/批注命令**,而是编排官方 `lark-*` 技能完成 I/O,自己只做官方不覆盖的领域逻辑。这是 fei2md 已确立、并在评审中定稿的架构模式,md2feishu 照搬以保证两个 skill 一致。

**背景**:在实现 fei2md 时发现 `larksuite/cli` 官方自带 AI Agent Skills,其中 `lark-doc`(文档读写,v2 API)、`lark-wiki`(知识节点)、`lark-drive`(文件+批注)已覆盖飞书评审的 I/O 层。自封装这些命令是重复造轮子,且会停留在已废弃的 v1 接口。

| 能力 | 由谁负责 | 说明 |
|------|---------|------|
| 文档读取(fetch markdown + block id) | **官方 lark-doc** | v2 命令,`--detail with-ids` 给 block id |
| 文档更新(str_replace / block_replace / append) | **官方 lark-doc** | v2 命令,八种 `--command` 指令 |
| wiki 节点 → 文档 token | **官方 lark-wiki / lark-drive +inspect** | token 转换 |
| 批注数量校验 | **官方 lark-drive** | comments list 计数 |
| 白板重建(mermaid 源) | **官方 lark-whiteboard** | `whiteboard +update` |
| **git diff 章节定位** | **本 skill** | `extract_section.py` |
| **Clean Copy 生成** | **本 skill** | `clean_copy.py` + `strip_metadata.py` |
| **策略 A/B/C 选路** | **本 skill** | 按章节是否含 `<!--feishu:...-->` 标记分流 |
| **同步后校验** | **本 skill** | `verify_sync.py` 对比前后快照 |
| **front matter sync 状态回写** | **本 skill** | `last_commit` / `last_synced_at` |

**做什么**:
- 读本地 markdown 的 front matter,拿到飞书文档绑定(`feishu-doc`)+ 上次同步基准(`sync.last_commit`)
- 用 `git diff <last_commit>..HEAD` 识别变更章节
- 对每个变更章节,检查是否含受保护元素标记,选策略 A/B/C
- 生成 Clean Copy(剥离本地元数据 + feishu 注释行)
- 委托官方 `lark-doc` 按 v2 指令推送
- 推送后 fetch 新状态,校验批注/白板/图片/章节结构数量不减少
- 回写本地 front matter 的 `sync.*` 字段

**不做什么**(明确排除):
- 自己封装 lark-cli 命令(委托官方技能)
- 拉取/分类/关闭批注(归 fei2md)
- v5 白板保护式 export→import(依赖 CLI 白板导出能力,尚未解锁)

---

## 2. v2 CLI 命令映射（关键）

工作法原文(§4.4、§7)写于 `lark-cli v1.0.0` 时代，用的是 v1 旧写法(`--mode replace_range --selection-by-title`、`--mode replace_all --selection-with-ellipsis`)。**本 skill 基于 v2 CLI 实际能力**（`lark-cli` 1.0.57+），下文命令均为 v2 实测可用写法。

> `--api-version` 是 deprecated 兼容性标志，CLI 默认使用 v2，无需显式传。

| 策略 | v2 CLI 命令 |
|------|-------------|
| 🟢 A 纯文本章节 | `docs +update --doc "$TOKEN" --command str_replace --doc-format markdown --pattern "## 标题...结束标志" --content "$(cat clean.md)"` |
| 🟡 B 含白板(source=mermaid) | `docs +fetch --doc "$TOKEN" --scope section --start-block-id <标题id> --detail with-ids` 取 block id → `block_replace` 逐个改文字 block(跳过白板)→ `whiteboard +update` 重建 mermaid |
| 🔴 C 含白板(source=manual) | 同 B 的 fetch+block_replace，但**白板零触碰**(manual 无源可重建) |

**省略号语法说明**：v2 Markdown 模式下 `--pattern` 支持 `前缀...后缀`，三个英文句点串联首尾，匹配从前缀到后缀的全部内容（含中间被省略部分），用 `--content` 整体替换。适合首尾特征明显的章节。

### 策略 C 的 v2 解锁（本 story 相对原草案的关键变更）

工作法 §8.3(2026-06-04 基线)记录「Block replace 快捷命令不存在」，§9 升级清单 #5 把 `docs +update --command block_replace` 列为待解锁项。

**现在 v2 已解锁**（lark-cli 1.0.57）：`docs +update --command block_replace --block-id <id> --content <xml>` 是一等命令。因此本 skill 的策略 C 从「仅文档化」升级为**可执行**。

**v1 降级方案**：若 CLI 版本低于 1.0.57，v2 标志不可用，降级为 v1 模式：`replace_range --selection-by-title`（策略 A）、`replace_range` 整章+占位符重建（策略 B 降级）、不可执行（策略 C）。

---

## 3. 输入输出契约

### 输入
- `<markdown 文件路径>`(必需):本地绑定飞书文档的 markdown 文件
- 文件 front matter 必须含 `feishu-doc` 字段
- 文件 front matter 的 `sync.last_commit` 提供 git diff 基准(缺失时视为首次全量推送)

### 输出
1. **飞书文档变更**:变更章节内容更新(由官方 lark-doc 执行,需用户确认)
2. **本地文件变更**:`front matter.sync` 字段更新、内联 `<!--feishu:whiteboard ...-->` token 更新
3. **终端报告**:变更章节清单 + 选定策略 + 校验结果

### 输出报告格式

```
┌─────────────────────────────────────────┐
│  md2feishu 增量同步（N 个变更章节）       │
│  文档：<feishu-title>                    │
│  基准 commit：abc123 → HEAD：def789      │
│                                         │
│  [1] ## 六 用户旅程        → 🟢 策略 A   │
│  [2] ### 2.1 总体架构      → 🟡 策略 B   │
│  [3] ### 2.2 部署架构      → 🔴 策略 C   │
│                                         │
│  校验：批注 5→5 ✅  白板 3→3 ✅          │
│        图片 4→4 ✅  章节 12→12 ✅        │
└─────────────────────────────────────────┘
```

---

## 4. 增量同步六步流程(工作法 §四)

| 步骤 | 动作 | 由谁做 |
|------|------|--------|
| 1 | 读 front matter → 取 `feishu-doc` + `sync.last_commit` | SKILL.md 指令(strip_metadata read-token) |
| 2 | `git diff <last_commit>..HEAD -- <file>` → 变更章节标题 | SKILL.md 指令 |
| 3 | 对每章节查 `<!--feishu:...-->` 标记 → 选 A/B/C | extract_section.py + 选路逻辑 |
| 4 | 生成 Clean Copy(strip_metadata + clean_copy)→ 委托 lark-doc 推送 | clean_copy.py + 官方技能 |
| 5 | fetch 新状态 → 回写本地内联 token + sync 字段 | SKILL.md 指令 |
| 6 | 校验:批注/白板/图片/章节结构 ≥ 同步前 | verify_sync.py + 官方技能计数 |

### Step 2:章节提取的正确终止条件(CRITICAL — 实验 E)

工作法实验 E 反复踩坑:章节提取终止条件若只匹配同级标题,遇到更高级标题会越界,导致 `replace_range` 后标题重复。

**正确规则**:提取终止条件必须是**「遇到任意 ≥ 当前层级的标题」**。

| 当前章节层级 | 正确终止条件 | 错误做法(会越界) |
|--------------|-------------|-------------------|
| H2 (`##`) | 遇到 `#` 或 `##` | 只匹配 `## ` |
| H3 (`###`) | 遇到 `#`、`##`、`###` | 只匹配 `### `(遇 H2 不停 ❌) |
| H4 (`####`) | 遇到 `#`~`####` | 同理 |
| H5 (`#####`) | 遇到任意标题 | 同理 |

测试物料正好覆盖实验 E 场景:`### 2.2 部署架构`(H3)后紧跟 `## 三、用户旅程`(H2)。

### Step 4:Clean Copy 规则

Push 前必须移除:
1. 本地元数据(front matter / comments 块 / h1 / 元数据 blockquote / 分隔线)— 由 `strip_metadata.py` 完成
2. 正文内所有 `<!--feishu:...-->` 注释行(HTML 注释会被飞书后端删除,留在内容里无意义)— 由 `clean_copy.py` 完成

**必须保留**:
- `<whiteboard type="blank"></whiteboard>` 占位符(触发飞书自动重建白板)
- 图片 markdown(`![alt](url)`)
- 批注快照块已在 strip_metadata 剥离,不会污染

---

## 5. front matter Schema

```yaml
---
feishu-doc: DBsowvkbAiVlTkkWXZec2W0PnHc      # wiki token（必填）
feishu-title: "CMI营销平台需求文档"            # 推荐
feishu-url: https://xxx.feishu.cn/wiki/...    # 推荐
sync:                                         # md2feishu 读写
  last_commit: abc123def456                   # 上次同步时的 git commit（diff 基准）
  last_synced_at: "2026-06-03T10:00:00+08:00" # 上次 push 时间戳
---
```

`sync.*` 字段只有 md2feishu 读写,fei2md 完全不读。两个 skill 通过同一 front matter 解耦。同步完成后 md2feishu 把 `last_commit` 更新为当前 HEAD、`last_synced_at` 更新为当前时间。

---

## 6. 策略矩阵(工作法 §8.5,v2 版)

```
                章节有受保护元素吗？
                          │
            ┌─────────────┼─────────────┐
            │             │             │
        纯文本         有白板/图片     有白板/图片
        无标记           source=         source=
            │           mermaid          manual
            │             │             │
        🟢 策略 A      🟡 策略 B       🔴 策略 C
      str_replace     block_replace    block_replace
      整章替换        + 白板重建        白板零触碰
      零风险
```

| 策略 | 文字更新方式 | 白板/图片处理 | 适用条件 |
|------|-------------|--------------|----------|
| 🟢 A | `str_replace` 整章(markdown 模式省略号语法) | 无需处理 | 章节内无 `<!--feishu:…-->` 标记 |
| 🟡 B | `block_replace` 逐个文字 block | `whiteboard +update` 按 mermaid 源重建 | 含 `source=mermaid` 标记 |
| 🔴 C | `block_replace` 逐个文字 block | **零触碰**,白板 token 不变 | 含 `source=manual` 标记 |

详细 v2 命令与适用条件见 `references/sync-strategy-matrix.md`。

---

## 7. 脚本设计(全部纯逻辑,不调 lark-cli)

| 脚本 | 职责 | 为什么是自有而非官方 |
|------|------|---------------------|
| `strip_metadata.py` | 剥离本地元数据(5 类) | 官方不管推送前的本地清洗(工作法规则 2) |
| `extract_section.py` | 按"≥ 当前层级"终止条件提章节 | 官方无 markdown 文件章节解析;修实验 E bug |
| `clean_copy.py` | 删 feishu 注释行、保留白板占位符 | 官方不管 Clean Copy 生成 |
| `verify_sync.py` | 对比同步前后快照 | 官方不做跨"本地/远端"的差分校验 |

`strip_metadata.py` 与 fei2md 版本**行为完全一致**(5 类剥离,同一实现)。两个 skill 各自持有一份(self-contained),这是工作法 §2 三层自包含结构的要求。

**为什么不共享一份**:skill 应自包含,部署时各自独立。两份保持一致靠共享的单元测试 + 行为一致性核对(见 §9)。

---

## 8. 错误处理

| 场景 | 处理 |
|------|------|
| 文件不存在 | 提示检查路径 |
| 无 front matter / 无 `feishu-doc` | 提示添加绑定 |
| 无 `sync.last_commit` | 视为首次推送,提示用户确认是否全量 |
| git 无变更 | 输出"✅ 本地与飞书已同步,无变更" |
| 推送后白板数减少 | ⚠️ 警告,提示检查策略选择是否误用 A |
| 推送后批注数减少 | ⚠️ 严重警告,提示可能误用了 overwrite |
| lark-cli 未登录 | 提示 `lark-cli auth login` |

---

## 9. 测试策略

| 测试对象 | 方法 |
|---------|------|
| `strip_metadata.py` | 复用 fei2md 的 5 类剥离单元测试(同一实现) |
| `extract_section.py` | **重点**:实验 E 回归(H3→H2 不越界)+ H2/H3/H4/H5 边界全覆盖,用测试物料真实文件 |
| `clean_copy.py` | 验证删 feishu 标记、留白板占位符和图片 |
| `verify_sync.py` | mock 同步前后快照,验证计数对比 |
| strip_metadata 一致性 | md2feishu 版与 fei2md 版对同一输入输出一致 |

**不实际 push 飞书**:脚本纯逻辑,推送由 SKILL.md 编排官方技能完成、需用户确认。测试物料文档仅用于本地逻辑验证。

---

## 10. 强制规则(工作法 §0.1,SKILL.md 必须内嵌)

1. **严禁 `overwrite` 模式**:批注锚定文本整体替换后 UI 不可见。唯一例外:首次空文档推送。
2. **推送前剥离本地元数据**:front matter / comments 块 / h1 / 元数据 blockquote / 分隔线,严禁进飞书正文。
3. **同步后追加 Git Commit 哈希**:飞书文档末尾追加 commit 哈希短版,便于追溯。
4. **多应用切换**:`lark-cli config init --app-id … --app-secret-stdin --brand feishu`。

---

## 11. 与 fei2md 的关系

| 维度 | fei2md | md2feishu |
|------|--------|-----------|
| 方向 | 飞书 → 本地(获取) | 本地 → 飞书(发布) |
| 只读? | 只读(唯一写飞书是关闭批注) | 写飞书(更谨慎) |
| 共享 front matter | 读 `feishu-*` | 读 `feishu-*` + 读写 `sync.*` |
| 共享 strip_metadata | ✅ 自有一份 | ✅ 自有一份(行为一致) |
| 独有领域逻辑 | 批注三类分类 | 章节 diff + 策略 A/B/C |
| 委托官方技能 | lark-doc/wiki/drive | lark-doc/wiki/drive/whiteboard |

两个 skill 逻辑独立,通过同一份本地 markdown(front matter + 内联标记)解耦,构成双向闭环。
