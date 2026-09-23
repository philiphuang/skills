# skills

个人公开 skill 仓——供 multica 等平台通过 GitHub URL 安装。

本仓为发布渠道，skill 由开发地同步更新。

## 目录结构

```
jiaofu/           交付套件（jf-*）——「高保真工作法」四层工作流
env-harness/           环境工具类——文档收发、IM 采集、飞书同步、项目脚手架等
```

## 安装

`skillshare install` 指向 skill 所在目录——分组下的带分组名，顶层的直接跟 skill 名：

```bash
skillshare install philiphuang/skills/jiaofu/jf-prd -p
skillshare install philiphuang/skills/env-harness/docness -p
```

`-p` 为项目模式，装到当前项目的 `.claude/skills/`。

## 技能清单

### jiaofu/ — 交付套件

入口是 `jf-router`：先解析意图落在四层工作流的哪个环节，再路由到对应 skill。
（下表按工作流顺序，非字典序。）

| 目录 | 说明 |
|------|------|
| `jf-router/` | 套件入口路由器——解析意图，强制路由到正确的 jf-* |
| `jf-mrd/` | MRD——把模糊想法钉成可评审的业务事实 |
| `jf-prd/` | PRD——业务事实转成可验收的需求规格 + 权限 |
| `jf-ia/` | IA——从 PRD 推导页面骨架和导航体系 |
| `jf-wireframe/` | 线框——EC 先行驱动，自包含可评审，含组件与状态变体 |
| `jf-uxprompt/` | UX 提示词——两套生成路径，每页自包含元提示词 |
| `jf-data/` | 数据建模——从业务实体推导数据域到物理表 |
| `jf-test/` | 测试——基于 PRD 验收标准做 BDD 场景和测试用例 |
| `jf-review/` | 评审——cherry pick 各 skill 产出，显性化成客户评审材料 |

安装地址：`https://github.com/philiphuang/skills/tree/main/jiaofu/<skill>`

### env-harness/ — 环境工具类

| 目录 | 说明 |
|------|------|
| `docness/` | 文档收发编排器——URL/本地/腾讯文档/飞书/录音 → Markdown 知识库，或 Markdown → 配图/PPT/Word/PDF → 飞书/腾讯文档 |
| `imness/` | 飞书 IM 会话与会议采集加工器——采集群聊/妙记，打码脱敏后建可维护知识库，提取候选任务 |
| `md2feishu/` | 本地 markdown 增量同步到飞书 wiki，保留批注/白板/图片 |
| `transcribe/` | 音频转文字，可选说话人分离与已知说话人提示 |
| `project-daimon/` | 项目初始化脚手架——Git/gitignore/Agent 环境多选/AGENTS.md/MCP/skill 启用 |
| `scene-switcher/` | 多角色 Skill 场景切换器——保存现场、切换预设、精确还原 |

安装地址：`https://github.com/philiphuang/skills/tree/main/env-harness/<skill>`
