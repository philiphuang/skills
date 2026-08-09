---
name: skill-publisher
description: Skill Factory 的发布/安装工具。在 skills-factory 仓库中用于把 products/ 下的 skill 发布到 skills-repo/ 并推送到 GitHub；在任意位置用于从 GitHub 通过 skillshare 安装 skill 到指定目录。
author: "@philiphuang"
version: 1.0.0
---

# Skill Publisher

> 把 Skill Factory 的两阶段部署封装成两个命令：发布到 GitHub 发布仓，或从 GitHub 安装到指定目录。

## 触发条件

以下任一情况触发此 Skill：

- 使用 `/skill-publisher` 命令
- 用户说「发布 skill」、「安装 skill」、「部署 skill」等

## 核心概念

- **skills-factory**（本仓库）：开发源仓，skill 的唯一真相来源在 `products/<skill>/`。
- **skills-repo/**：本仓库内的独立 git 子目录，remote 指向 `philiphuang/skills`，是发布仓。
- **发布流程**：从 `products/` 复制 skill 到 `skills-repo/`，自动剥离测试代码，然后 `git add/commit/push`。
- **安装流程**：从 GitHub 拉取指定 skill，通过 `skillshare` 部署到用户指定的目标目录。

## 用法

### 发布

```bash
python3 products/skill-publisher/scripts/skill_publisher.py publish <skill-name>
```

选项：

- `--message` / `-m`：自定义 git commit 信息（默认 `release: <skill-name>`）
- `--dry-run` / `-n`：预览，不实际执行
- `--force` / `-f`：直接覆盖 `skills-repo/` 中已存在的同名 skill，不提示

### 安装

```bash
python3 products/skill-publisher/scripts/skill_publisher.py install <skill-name> <target-dir>
```

选项：

- `--dry-run` / `-n`：预览，不实际执行
- `--force` / `-f`：强制覆盖（传递给 skillshare）
- `--remote <repo>`：指定 GitHub 仓库（默认 `philiphuang/skills`）

## 工作流程

### 发布流程

1. 检查当前目录是否为 skills-factory 仓库根目录。
2. 检查 `products/<skill-name>/SKILL.md` 是否存在。
3. 调用 `scripts/deploy_skill.py <skill-name> --skills-repo --force`，自动剥离 `tests/`、`evals/`、`__pycache__/` 等测试代码。
4. 进入 `skills-repo/`，`git add <skill-name>/`。
5. 如果工作区有变更，创建 commit 并 push 到 `origin`。
6. 报告发布结果。

### 安装流程

1. 检查 `skillshare` CLI 是否已安装。
2. 确保 `<target-dir>` 存在（不存在则创建）。
3. 在 skillshare 中注册一个临时 target 指向 `<target-dir>`。
4. 从 GitHub 安装指定 skill 到 skillshare 全局 source：`skillshare install <remote> -s <skill-name> -g`。
5. 同步到临时 target：`skillshare sync <temp-target>`。
6. 移除临时 target，避免污染用户配置。
7. 验证 `<target-dir>/<skill-name>/SKILL.md` 是否存在，报告结果。

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
- 安装命令会临时修改 skillshare 的 target 配置，执行完成后自动清理。
- 如果目标目录已经存在同名 skill，请使用 `--force` 覆盖，或在执行前手动备份。
