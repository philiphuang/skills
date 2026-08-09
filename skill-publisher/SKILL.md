---
name: skill-publisher
description: Skill Factory 的发布/安装一体化工具。通过 /publish 命令发布 skill 到 GitHub；若同时提供目标目录，则先确保 skill 已发布，再用 skillshare 项目模式安装到该目录。
author: "@philiphuang"
version: 1.0.0
---

# Skill Publisher

> 单一命令 `/publish` 覆盖 Skill Factory 的两阶段部署：发布到 GitHub；若给定目标目录，则再安装到该目录。

## 触发条件

以下任一情况触发此 Skill：

- 使用 `/skill-publisher` 或 `/publish` 命令
- 用户说「发布 skill」、「安装 skill」、「部署 skill」等

## 核心概念

- **skills-factory**（本仓库）：开发源仓，skill 的唯一真相来源在 `products/<skill>/`。
- **skills-repo/**：本仓库内的独立 git 子目录，remote 指向 `philiphuang/skills`，是发布仓。
- **已发布**：`skills-repo/<skill>/SKILL.md` 存在，表示该 skill 已经过发布流程进入发布仓。
- **目标目录**：用户希望安装 skill 的项目目录。`skillshare` 会在该目录下以项目模式（`-p`）工作，读取/创建 `.skillshare/config.yaml` 并使用其中已有的 target 配置。

## 用法

```bash
python3 products/skill-publisher/scripts/skill_publisher.py publish <skill-name> [<target-dir>]
```

### 仅发布（不带目标目录）

```bash
python3 products/skill-publisher/scripts/skill_publisher.py publish todo-workflow
```

流程：
1. 从 `products/todo-workflow/` 复制到 `skills-repo/todo-workflow/`。
2. 自动剥离 `tests/`、`evals/`、`__pycache__/`、`*.pyc` 等测试/开发文件。
3. 在 `skills-repo/` 中 `git add/commit/push` 到 `origin`。

### 发布并安装到目标目录

```bash
python3 products/skill-publisher/scripts/skill_publisher.py publish todo-workflow /path/to/project
```

流程：
1. 检查 `skills-repo/<skill>/SKILL.md` 是否存在。
   - 不存在：先走完整发布流程（products → skills-repo → git push）。
   - 存在：跳过发布。
2. 进入 `<target-dir>`，若不存在则创建。
3. 用 `skillshare init -p` 初始化项目配置（若已初始化则跳过）。
4. 用 `skillshare install philiphuang/skills -s <skill> -p` 从 GitHub 安装 skill 到项目 source。
5. 执行 `skillshare sync -p`，按项目 `.skillshare/config.yaml` 中已有的 target 配置同步到目标目录。

### 选项

- `--message` / `-m`：自定义 git commit 信息（默认 `release: <skill-name>`）
- `--dry-run` / `-n`：预览，不实际执行
- `--force` / `-f`：发布时直接覆盖 `skills-repo/` 中已存在的同名 skill；安装时强制覆盖
- `--remote <repo>`：指定 GitHub 发布仓（默认 `philiphuang/skills`）

## 返回码

| 码 | 含义 |
|----|------|
| 0  | 成功 |
| 1  | 参数错误或环境检查失败 |
| 2  | 用户取消 |
| 3  | 部署/安装失败 |
| 4  | git 操作失败 |
| 5  | skillshare 未安装或调用失败 |

## 注意事项

- 发布命令必须在 `skills-factory/` 仓库根目录执行。
- 当提供 `<target-dir>` 时，skillshare 使用项目模式（`-p`），依赖目标目录的 `.skillshare/config.yaml` 中已有的 target 配置进行 sync。
- 若 skill 尚未发布，脚本会先执行发布并推送到 GitHub，再执行安装。
