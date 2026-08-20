---
name: scene-switcher
description: 多角色 Skill 场景切换器。当用户需要在同一项目里按角色（研究/产品/文档等）切换 Skill 集合、切换前保存现场快照、切回时从快照精确还原时使用。基于 Skillshare 多全局配置 + sync，提供 scene save / activate / profile / restore / status / list / doctor 命令与全局 skill-profile（一参切换、零参保存），全部支持 --dry-run。
argument-hint: "<save|activate <preset>|restore|status|list|doctor> [--dry-run]"
user-invocable: true
---

# scene-switcher

同一项目经常扮演多个角色（研究、产品经理、文档导入导出等），每个角色需要不同的 Skill 集合；
Skill 一多，agent 的 always-loaded 上下文就被吃掉一大块。本 skill 提供**场景切换**能力：

- 会话内热切换 Skill 集合（Claude Code 热加载；Codex 删除语义见下方「已知限制」）
- 角色（预设场景）全局定义、跨项目一致
- 预设期间项目自定义 Skill **必须不存在**；切回时从快照**精确还原现场**

实现路线（issue #88 已锁定）：**Skillshare 多配置 + `sync`**，快照/还原由一层薄编排脚本（`scene`）完成。

## 命令面（当前已实现）

```text
scene save [name] [--force] [--dry-run]  保存现场快照为 <name>（缺省 default；quarantine 项目自定义 Skill）
scene activate <preset> [--dry-run]    切换到预设 profile（无 default 快照时自动先 save）
scene profile [name]                   无参：保存当前 skill 集合为项目 profile；带参：切换并记录 current-profile
scene restore [name] [--dry-run]       按 <name> 从快照精确还原（缺省 default）
scene status [name]                    当前场景/快照时间/quarantine/漂移报告
scene list                             预设与快照清单
scene doctor                           体检：读取目录/版本/profile/锁/快照完整性
```

### skill-profile（全局命令）

安装后可直接在任意项目调用（`~/.local/bin/skill-profile`）：

```text
skill-profile             保存当前 skill 集合为项目 profile（名字取 current-profile，空则 default）
skill-profile <name>      切换到 <name>（项目级 .skillshare/profiles/<name>.yaml 优先，其次全局）
```

- 当前 profile 名字记录在 `<项目根>/.skillshare/profiles/current-profile.yaml`（空 = default）
- `scene restore` 后会清空 current-profile（回到自定义现场）

## 预设 profile（FR5）

- 定义位置与优先级：**项目级** `<project-root>/.skillshare/profiles/<preset>.yaml` **优先**，其次
  **全局** `<skillshare-config-dir>/profiles/<preset>.yaml`（默认 `~/.config/skillshare/profiles/`）——
  同名时项目级覆盖全局（便于项目定制预设）；`skill-profile <name>` 即按此优先级切换
- 格式：标准 Skillshare 全局配置（`sources.skills` + `mode: merge` + `targets`）
- **targets 必须覆盖全部 scene 读取点**：`claude` / `codex` / `universal`
  （`~/.claude/skills`、`~/.codex/skills`、`~/.agents/skills`）——缺任一 target，
  `scene activate` 会拒绝执行（预设期会泄漏自定义 Skill）
- `include` 用 filepath.Match glob 指向中央库目录分组；改动后可用
  `SKILLSHARE_CONFIG=<profile> skillshare sync -g --dry-run` 验证
- 示例：`products/scene-switcher/profiles/research.example.yaml` → 复制到运行时目录改名使用

## 工作机制

- **项目级存储（统一在 `.skillshare/profiles/`）**：快照 `<name>/`（scene.yaml/quarantine/restore-profile）、
  项目级 profile `<name>.yaml`、当前 profile 名 `current-profile.yaml` 三者在同一目录。
  `SCENE_SCENES_ROOT` 可显式覆盖，无 git 环境时回退 `<skillshare-config-dir>/scenes/`。
  `scene save` 不传名字时快照名为 `default`；传名字则按名字保存，`scene restore <name>` 按同一名字复原，
  多份快照彼此独立、可并存。`scene activate` 的现场载体固定为 `default`。save 后建议把
  `.skillshare/profiles/*/` 加入项目 `.gitignore`（快照含 quarantine 文件副本，不应提交；项目级 profile
  `*.yaml` 与 `current-profile.yaml` 可保留提交共享）
- **读取点**：全局层只管理 `claude`/`codex`/`universal` 三个 skillshare target（对应
  `~/.claude/skills`、`~/.codex/skills`、`~/.agents/skills`，可用 `SCENE_TARGETS` 覆盖），
  项目层扫描 `<repo>/.agents/skills`、`<repo>/.claude/skills`、`<repo>/.codex/skills`
- **条目分类**（写 scene.yaml）：管理链接（软链且目标在 `~/.skills-src/` 内）、本地目录（移入 quarantine，
  保留原相对路径）、**跨读取点软链**（软链目标在另一 scene 读取点内，如 `~/.claude/skills/lark-base ->
  ../../agents/skills/lark-base`——目标条目被 quarantine 后软链会悬空，故软链本身一并 quarantine，restore 移回）、
  unmanaged（悬空/源外软链——不动、不删，restore 原样保留）
- **restore**：用 `restore-profile.yaml`（include 为快照管理链接精确 name，S2 已验证可精确重建；
  空快照用不匹配 glob `__scene_none__`）跑 `skillshare sync -g`，然后移回 quarantine（S3 已验证
  merge 模式保留本地真实目录），保留预设期新增，快照归档保留最近 5 份

## 安全边界（NFR）

1. **顶层读取目录永不删除/替换**——一切变更只发生在已存在目录内部
2. 一切「移除」= 移入 quarantine 可找回；未识别条目永不删除
3. 全程可 `--dry-run`（零文件系统变更）；`.lock` 互斥 + 残留锁自动清理
4. 依赖仅 skillshare / git / jq；`SKILLSHARE_CONFIG` 指向预设 profile 或沙箱 config 时场景根自动跟随

## 已知限制

- **Codex 删除语义**（S1 结论）：新增/变更自动检测；**删除不保证热生效**——`scene restore` 后若
  Codex 会话内技能列表未更新，请重启 Codex。Claude Code 侧删除/新增均热生效（官方 live change detection）
- unmanaged 条目若在预设期被外部 sync 清理，restore 不负责复活（外部删除超出快照职责）；
  指向另一 scene 读取点的软链因会被一并 quarantine，不在此列（见「条目分类」）
- copy 模式 target（如 `~/.zcode/skills`）不在 scene 管理范围（`SCENE_TARGETS` 默认只含
  claude/codex/universal），不会被误 quarantine

## 环境要求

- skillshare v0.20.25（`SKILLSHARE_CONFIG` env 未文档化 → 钉住此版本）
- 中央库 `~/.skills-src`（Skillshare 单一来源，scene 只读它）
