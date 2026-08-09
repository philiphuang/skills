#!/usr/bin/env python3
"""skill_publisher.py — Skill Factory 发布/安装一体化入口。

单一命令：publish <skill-name> [<target-dir>]
- 只带 skill-name：把 products/<skill>/ 发布到 skills-repo/<skill>/ 并推送到 GitHub。
- 带 target-dir：先确保 skill 已发布（未发布则先发布），再用 skillshare 项目模式安装到目标目录。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 返回码
RC_OK = 0
RC_PARAM_ERROR = 1
RC_USER_CANCEL = 2
RC_DEPLOY_ERROR = 3
RC_GIT_ERROR = 4
RC_SKILLSHARE_ERROR = 5

# 默认 GitHub 发布仓
DEFAULT_REMOTE = "philiphuang/skills"

# 需要剥离的测试/开发目录与文件后缀
STRIP_DIRS = {"tests", "evals", "__pycache__", ".pytest_cache", ".mypy_cache"}
STRIP_SUFFIXES = (".pyc", ".pyo", ".bak")


def run(cmd: list[str], cwd: Path | None = None, check: bool = True, capture: bool = False, input_text: str | None = None) -> subprocess.CompletedProcess:
    """执行子进程命令，失败时抛出 CalledProcessError。"""
    kwargs = {"cwd": cwd, "text": True}
    if capture:
        kwargs["capture_output"] = True
    if input_text is not None:
        kwargs["input"] = input_text
    return subprocess.run(cmd, check=check, **kwargs)


def find_repo_root() -> Path:
    """通过 git 找到当前仓库根目录。"""
    result = run(["git", "rev-parse", "--show-toplevel"], capture=True)
    return Path(result.stdout.strip())


def is_skills_factory_repo(repo_root: Path) -> bool:
    """检查给定目录是否是 skills-factory 仓库。"""
    return (repo_root / "products").is_dir() and (repo_root / "skills-repo").is_dir()


def strip_tests(skill_dir: Path) -> list[str]:
    """从 skill 目录中删除测试/开发文件，返回被删除的相对路径列表。"""
    removed: list[str] = []
    for root, dirs, files in os.walk(skill_dir, topdown=False):
        root_path = Path(root)
        for d in list(dirs):
            if d in STRIP_DIRS:
                target = root_path / d
                shutil.rmtree(target)
                removed.append(str(target.relative_to(skill_dir)))
        for f in files:
            if f.endswith(STRIP_SUFFIXES):
                target = root_path / f
                target.unlink()
                removed.append(str(target.relative_to(skill_dir)))
    return removed


def do_copy(source: Path, target: Path) -> None:
    """复制 source 目录到 target，先删除已存在的 target。"""
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)


def publish_skill(skill_name: str, repo_root: Path, message: str | None = None, force: bool = False, dry_run: bool = False) -> int:
    """把 products/<skill>/ 发布到 skills-repo/<skill>/ 并推送到 GitHub。

    返回 0 表示成功，非 0 表示失败。
    """
    source = repo_root / "products" / skill_name
    if not (source / "SKILL.md").is_file():
        print(f"错误：products/{skill_name}/SKILL.md 不存在", file=sys.stderr)
        return RC_PARAM_ERROR

    skills_repo = repo_root / "skills-repo"
    target = skills_repo / skill_name

    if dry_run:
        print(f"[DRY RUN] 将发布 {skill_name}:")
        print(f"  来源: {source}")
        print(f"  目标: {target}")
        print(f"  剥离: tests/ evals/ __pycache__/ *.pyc *.pyo *.bak")
        print(f"  git:  add/commit/push in {skills_repo}")
        return RC_OK

    try:
        tmpdir = Path(tempfile.mkdtemp(prefix=f"skill_publisher_{skill_name}_"))
        staged = tmpdir / skill_name
        shutil.copytree(source, staged)
        removed = strip_tests(staged)

        do_copy(staged, target)
        shutil.rmtree(tmpdir)

        if removed:
            print(f"已剥离 {len(removed)} 项测试/开发文件")
    except OSError as e:
        print(f"错误：部署到 skills-repo 失败: {e}", file=sys.stderr)
        return RC_DEPLOY_ERROR

    try:
        result = run(["git", "status", "--porcelain", "--", skill_name], cwd=skills_repo, capture=True)
        if not result.stdout.strip():
            print(f"ℹ️  skills-repo/{skill_name} 无变更，无需提交")
            return RC_OK

        run(["git", "add", "--", skill_name], cwd=skills_repo)
        commit_message = message or f"release: {skill_name}"
        run(["git", "commit", "-m", commit_message], cwd=skills_repo)
        run(["git", "push"], cwd=skills_repo)
        print(f"✅ 已发布 {skill_name} 到 skills-repo/ 并推送到 GitHub")
        return RC_OK
    except subprocess.CalledProcessError as e:
        print(f"错误：git 操作失败: {e}", file=sys.stderr)
        return RC_GIT_ERROR


def is_published(skill_name: str, repo_root: Path) -> bool:
    """检查 skills-repo/<skill>/SKILL.md 是否存在。"""
    return (repo_root / "skills-repo" / skill_name / "SKILL.md").is_file()


def ensure_skillshare() -> bool:
    """检查 skillshare CLI 是否可用。"""
    return shutil.which("skillshare") is not None


def install_skill(skill_name: str, target_dir: Path, remote: str, force: bool = False, dry_run: bool = False) -> int:
    """用 skillshare 项目模式把 skill 安装到目标目录。

    返回 0 表示成功，非 0 表示失败。
    """
    if not ensure_skillshare():
        print("错误：未找到 skillshare CLI，请先安装 skillshare", file=sys.stderr)
        return RC_SKILLSHARE_ERROR

    if dry_run:
        print(f"[DRY RUN] 将安装 {skill_name} 到 {target_dir}:")
        print(f"  来源: {remote}")
        print(f"  命令:")
        print(f"    skillshare init -p")
        print(f"    skillshare install {remote} -s {skill_name} -p")
        print(f"    skillshare sync -p")
        return RC_OK

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 初始化项目配置（已存在则幂等跳过）
        run(["skillshare", "init", "-p"], cwd=target_dir)

        # 从 GitHub 安装 skill 到项目 source
        install_cmd = ["skillshare", "install", remote, "-s", skill_name, "-p"]
        if force:
            install_cmd.append("--force")
        run(install_cmd, cwd=target_dir)

        # 按项目已有 target 配置同步
        run(["skillshare", "sync", "-p"], cwd=target_dir)

        print(f"✅ 已安装 {skill_name} 到 {target_dir}（通过 skillshare 项目模式）")
        return RC_OK
    except subprocess.CalledProcessError as e:
        print(f"错误：skillshare 调用失败: {e}", file=sys.stderr)
        return RC_SKILLSHARE_ERROR


def cmd_publish(args: argparse.Namespace) -> int:
    """publish 命令实现。"""
    skill_name = args.skill_name
    target_dir: Path | None = Path(args.target_dir).expanduser().resolve() if args.target_dir else None
    dry_run = args.dry_run
    force = args.force
    message = args.message
    remote = args.remote or DEFAULT_REMOTE

    # 1. 确认在 skills-factory 仓库
    try:
        repo_root = find_repo_root()
    except subprocess.CalledProcessError:
        print("错误：当前目录不是 git 仓库，无法确定 skills-factory 根目录", file=sys.stderr)
        return RC_PARAM_ERROR

    if not is_skills_factory_repo(repo_root):
        print(f"错误：当前仓库不是 skills-factory（缺少 products/ 或 skills-repo/）：{repo_root}", file=sys.stderr)
        return RC_PARAM_ERROR

    # 2. 仅发布
    if target_dir is None:
        return publish_skill(skill_name, repo_root, message=message, force=force, dry_run=dry_run)

    # 3. 发布并安装：先确保已发布
    if not is_published(skill_name, repo_root):
        print(f"ℹ️  {skill_name} 尚未发布，先执行发布流程...")
        rc = publish_skill(skill_name, repo_root, message=message, force=force, dry_run=dry_run)
        if rc != RC_OK:
            return rc
    else:
        print(f"ℹ️  {skill_name} 已发布，跳过发布流程")

    # 4. 安装到目标目录
    return install_skill(skill_name, target_dir, remote, force=force, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill_publisher.py",
        description="Skill Factory 发布/安装一体化工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pub = subparsers.add_parser("publish", help="发布 skill；若提供目标目录则同时安装")
    pub.add_argument("skill_name", help="要发布/安装的 skill 名称（products/ 下的子目录名）")
    pub.add_argument("target_dir", nargs="?", help="目标项目目录（可选，提供则同时安装）")
    pub.add_argument("-m", "--message", help="git commit 信息")
    pub.add_argument("-n", "--dry-run", action="store_true", help="预览，不实际执行")
    pub.add_argument("-f", "--force", action="store_true", help="直接覆盖已存在的 skill")
    pub.add_argument("--remote", help=f"GitHub 发布仓（默认 {DEFAULT_REMOTE}）")

    args = parser.parse_args(argv)
    if args.command == "publish":
        return cmd_publish(args)
    parser.print_help()
    return RC_PARAM_ERROR


if __name__ == "__main__":
    sys.exit(main())
