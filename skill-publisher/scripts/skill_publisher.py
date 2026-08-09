#!/usr/bin/env python3
"""skill_publisher.py — Skill Factory 发布/安装双流程入口。

发布：把 products/<skill>/ 部署到 skills-repo/<skill>/ 并推送到 GitHub。
安装：从 GitHub 通过 skillshare 把指定 skill 部署到用户指定的目标目录。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
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


def run(cmd: list[str], cwd: Path | None = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """执行子进程命令，失败时抛出 CalledProcessError。"""
    kwargs = {"cwd": cwd, "text": True}
    if capture:
        kwargs["capture_output"] = True
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


def cmd_publish(args: argparse.Namespace) -> int:
    """发布命令实现。"""
    skill_name = args.skill_name
    dry_run = args.dry_run
    force = args.force

    # 1. 确认在 skills-factory 仓库
    try:
        repo_root = find_repo_root()
    except subprocess.CalledProcessError:
        print("错误：当前目录不是 git 仓库，无法确定 skills-factory 根目录", file=sys.stderr)
        return RC_PARAM_ERROR

    if not is_skills_factory_repo(repo_root):
        print(f"错误：当前仓库不是 skills-factory（缺少 products/ 或 skills-repo/）：{repo_root}", file=sys.stderr)
        return RC_PARAM_ERROR

    source = repo_root / "products" / skill_name
    if not (source / "SKILL.md").is_file():
        print(f"错误：products/{skill_name}/SKILL.md 不存在", file=sys.stderr)
        return RC_PARAM_ERROR

    skills_repo = repo_root / "skills-repo"
    target = skills_repo / skill_name

    # 2. 剥离测试代码并复制
    if dry_run:
        print(f"[DRY RUN] 将发布 {skill_name}:")
        print(f"  来源: {source}")
        print(f"  目标: {target}")
        print(f"  剥离: tests/ evals/ __pycache__/ *.pyc *.pyo *.bak")
        print(f"  git:  add/commit/push in {skills_repo}")
        return RC_OK

    try:
        # 复制到临时目录后剥离
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

    # 3. git 操作
    try:
        # 检查是否有变更
        result = run(["git", "status", "--porcelain", "--", skill_name], cwd=skills_repo, capture=True)
        if not result.stdout.strip():
            print(f"ℹ️  skills-repo/{skill_name} 无变更，无需提交")
            return RC_OK

        run(["git", "add", "--", skill_name], cwd=skills_repo)
        message = args.message or f"release: {skill_name}"
        run(["git", "commit", "-m", message], cwd=skills_repo)
        run(["git", "push"], cwd=skills_repo)
        print(f"✅ 已发布 {skill_name} 到 skills-repo/ 并推送到 GitHub")
        return RC_OK
    except subprocess.CalledProcessError as e:
        print(f"错误：git 操作失败: {e}", file=sys.stderr)
        return RC_GIT_ERROR


def ensure_skillshare() -> bool:
    """检查 skillshare CLI 是否可用。"""
    return shutil.which("skillshare") is not None


def cmd_install(args: argparse.Namespace) -> int:
    """安装命令实现。"""
    skill_name = args.skill_name
    target_dir = Path(args.target_dir).expanduser().resolve()
    dry_run = args.dry_run
    force = args.force
    remote = args.remote or DEFAULT_REMOTE

    if not ensure_skillshare():
        print("错误：未找到 skillshare CLI，请先安装 skillshare", file=sys.stderr)
        return RC_SKILLSHARE_ERROR

    if dry_run:
        print(f"[DRY RUN] 将安装 {skill_name}:")
        print(f"  来源: {remote}")
        print(f"  目标目录: {target_dir}")
        print(f"  命令: skillshare target add / install / sync / remove")
        return RC_OK

    # 确保目标目录存在
    target_dir.mkdir(parents=True, exist_ok=True)

    # 临时 target 名称
    temp_target = f"skill-publisher-{uuid.uuid4().hex[:8]}"

    try:
        # 1. 添加临时 target
        run(["skillshare", "target", "add", temp_target, str(target_dir), "-g"])

        # 2. 从 GitHub 安装 skill 到全局 source
        install_cmd = ["skillshare", "install", remote, "-s", skill_name, "-g"]
        if force:
            install_cmd.append("--force")
        run(install_cmd)

        # 3. 同步到临时 target
        run(["skillshare", "sync", temp_target, "-g"])

        # 4. 验证
        installed = target_dir / skill_name / "SKILL.md"
        if not installed.is_file():
            print(f"错误：安装后未找到 {installed}", file=sys.stderr)
            return RC_DEPLOY_ERROR

        print(f"✅ 已安装 {skill_name} → {target_dir / skill_name}")
        return RC_OK
    except subprocess.CalledProcessError as e:
        print(f"错误：skillshare 调用失败: {e}", file=sys.stderr)
        return RC_SKILLSHARE_ERROR
    finally:
        # 5. 清理临时 target
        try:
            run(["skillshare", "target", "remove", temp_target, "-g"], check=False)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill_publisher.py",
        description="Skill Factory 发布/安装双流程工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # publish
    pub = subparsers.add_parser("publish", help="发布 skill 到 skills-repo/ 并推送到 GitHub")
    pub.add_argument("skill_name", help="要发布的 skill 名称（products/ 下的子目录名）")
    pub.add_argument("-m", "--message", help="git commit 信息")
    pub.add_argument("-n", "--dry-run", action="store_true", help="预览，不实际执行")
    pub.add_argument("-f", "--force", action="store_true", help="直接覆盖已存在的 skill")

    # install
    inst = subparsers.add_parser("install", help="从 GitHub 安装 skill 到指定目录")
    inst.add_argument("skill_name", help="要安装的 skill 名称")
    inst.add_argument("target_dir", help="目标目录路径")
    inst.add_argument("-n", "--dry-run", action="store_true", help="预览，不实际执行")
    inst.add_argument("-f", "--force", action="store_true", help="强制覆盖")
    inst.add_argument("--remote", help=f"GitHub 仓库（默认 {DEFAULT_REMOTE}）")

    args = parser.parse_args(argv)

    if args.command == "publish":
        return cmd_publish(args)
    if args.command == "install":
        return cmd_install(args)

    parser.print_help()
    return RC_PARAM_ERROR


if __name__ == "__main__":
    sys.exit(main())
