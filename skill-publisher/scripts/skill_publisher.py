#!/usr/bin/env python3
"""skill_publisher.py — Skill Factory 发布/安装一体化入口。

单一命令：publish <skill-name> [<target-dir>]
- 只带 skill-name：把 products/<skill>/ 发布到 skills-repo/<group>/<skill>/ 并推送到 GitHub。
- 带 target-dir：先确保 skill 已发布（未发布则先发布），再用 skillshare 项目模式安装到目标目录。

<group> 由 skill 名推导：jf-* 交付套件 → jiaofu/，其余工具类 → env-harness/；
仓管理工具 skill-publisher → 顶层（不分组）。
"""

import argparse
import fnmatch
import os
import re
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
# 散落在 tests/ 之外的测试文件（如 scripts/test_foo.py）同样不该进发布仓（fnmatch 模式）
STRIP_PATTERNS = ("test_*.py", "*_test.py", "conftest.py", "test_*.sh", "*_test.sh")

# 发布仓 skills-repo/ 的分组（DEPLOYMENT_SPEC §2.4）：
# jf-* 交付套件 → jiaofu/；仓管理工具 → 顶层（不分组）；其余工具类 → env-harness/。
SKILLS_REPO_GROUP_JF = "jiaofu"
SKILLS_REPO_GROUP_DEFAULT = "env-harness"
# 管理本仓自身的 skill 直接放发布仓顶层：它们是仓的组成部分，不归任何工具分组。
SKILLS_REPO_TOP_LEVEL = frozenset({"skill-publisher"})


def resolve_skills_repo_group(skill_name: str) -> str:
    """推导 skill 在发布仓里的分组目录名；空字符串表示顶层。"""
    if skill_name in SKILLS_REPO_TOP_LEVEL:
        return ""
    return SKILLS_REPO_GROUP_JF if skill_name.startswith("jf-") else SKILLS_REPO_GROUP_DEFAULT


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


def matches_strip_pattern(filename: str) -> bool:
    """判断文件名是否命中 STRIP_PATTERNS（测试文件模式）。"""
    return any(fnmatch.fnmatch(filename, pattern) for pattern in STRIP_PATTERNS)


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
            if f.endswith(STRIP_SUFFIXES) or matches_strip_pattern(f):
                target = root_path / f
                target.unlink()
                removed.append(str(target.relative_to(skill_dir)))
    return removed

# 发布前引用可用性检查：相对路径引用（不含绝对路径/URL/占位符）
# 按模式分组：模式 → 提示文案
REF_PATTERNS: list[tuple[str, str]] = [
    # 依赖 skill 包内其他文件（references/ scripts/ assets/ 等）——引用自身包内文件，允许
    (r"(?<![A-Za-z])(references|scripts|assets|\.env\.example|\.skillignore)([a-zA-Z0-9._/\\-]*)\.(md|py|sh|json|yaml|yml|template)",
     "包内引用"),
    # 指向仓库其他区域（.scratch/ src/ 及多层 ../ 向上越出包目录）——脱离仓库后不可用。
    # 要求引用有文件后缀，避免误报省略号（...）、纯目录名等非文件引用。
    (r"(\.scratch/|src/|\.\./\.\./)([a-zA-Z0-9._/\\-]*)\.(md|py|sh|json|yaml|yml|template)",
     "仓库外引用"),
]

# 绝对路径模式（跨机器失效，必须改为 ~ 用户级路径）：
# /Users/<user>/、/home/<user>/ 等写死用户名的本地绝对路径
ABSOLUTE_PATH_PATTERNS = [
    r"/Users/[A-Za-z0-9._-]+/",  # macOS
    r"/home/[A-Za-z0-9._-]+/",   # Linux
]

# 允许的仓库外引用目标（声明性白名单：仓库内才存在、脱离仓库后明确不可用的文件）
ALLOWED_EXTERNAL_REFS = {
    "src/工作法/高保真/高保真工作法.md",  # jf-router 工作法来源（仅指路，路由分类不依赖）
    "src/jf-router/research/signal-words.md",  # 已迁移至 references/，此处仅指路
}

def _is_url_ref(line: str, match_start: int) -> bool:
    """判断引用是否嵌在 URL 中（如 [x](https://github.com/.../src/foo.md)）。

    URL 链接是有效的外部引用（浏览器可打开），不是"skill 脱离仓库后缺文件"的依赖。
    扫描匹配点所在整行的行首到匹配起点，找 URL 标记（:// 或 github.com/）。
    """
    prefix = line[:match_start]
    # 取匹配点所在行的最近 200 字符（覆盖长 URL）
    return "://" in prefix[-200:] or "github.com/" in prefix[-200:]

def _is_untracked_description(line: str) -> bool:
    """判断引用是否出现在纯描述文本中（非文件链接/代码/路径引用上下文）。

    排除：普通散文（...省略号）、环境路径（/opt/prjs/asserts/skills-src/...、.agents/skills/... 等运行时位置）、
    `docs/` 等文档目录描述。这些不构成"skill 脱离仓库后缺文件"的依赖。
    """
    stripped = line.strip()
    # 省略号（散文）
    if stripped in ("...", "……") or "..." in stripped.replace("只有", "").replace("……", ""):
        # 只有...才能 这类中文省略用法不算
        if "..." in stripped and not stripped.startswith((".", "/", "`", "[", "-", ">", "~")):
            return True
    # 运行时环境路径（/opt/prjs/asserts/skills-src、.agents/skills、docs/ 等，非相对依赖）
    if "~/" in line or ".agents/" in line or "docs/" in line or "skills-src" in line:
        return True
    return False

def check_ref_availability(source: Path) -> list[str]:
    """扫描 skill 包内所有文本文件中的路径引用。

    两类检查：
    1. 相对路径引用（SKILL.md 与 references/*.md）：引用目标不在包内 → 不可用
    2. 绝对路径（全部文本文件）：/Users/<user>/、/home/<user>/ → 跨机器失效

    返回不可用引用列表（空 = 全部可用）。每个条目为 "文件 → 引用的路径"。
    """
    problems: list[str] = []
    md_files = [source / "SKILL.md"] + sorted((source / "references").glob("*.md")) if (source / "references").is_dir() else [source / "SKILL.md"]

    for md in md_files:
        if not md.is_file():
            continue
        for line_no, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, label in REF_PATTERNS:
                for m in re.finditer(pattern, line):
                    ref = m.group(0).rstrip("`")  # 去掉可能的代码围栏
                    if not ref.strip():
                        continue
                    # 只检查仓库外引用；仓库内引用跳过
                    if label == "包内引用":
                        continue
                    if ref in ALLOWED_EXTERNAL_REFS:
                        continue
                    # URL 中的 src/（如 github 链接）不是仓库外相对引用
                    if _is_url_ref(line, m.start()):
                        continue
                    # 纯描述文本/运行时环境路径（~/.agents/ 等）不是文件依赖
                    if _is_untracked_description(line):
                        continue
                    problems.append(f"{md.name}:{line_no}: 仓库外引用 `{ref}`")

    # 绝对路径检查：扫描包内全部文本文件（SKILL.md/references/scripts/assets）
    for root, _dirs, files in os.walk(source):
        # 跳过会被剥离的目录
        if any(part in STRIP_DIRS for part in Path(root).relative_to(source).parts):
            continue
        for fname in files:
            fpath = Path(root) / fname
            if fname.endswith(STRIP_SUFFIXES) or fname.startswith(".") or matches_strip_pattern(fname):
                continue
            try:
                text = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue  # 二进制文件跳过
            rel = fpath.relative_to(source)
            for line_no, line in enumerate(text.splitlines(), 1):
                for apattern in ABSOLUTE_PATH_PATTERNS:
                    m = re.search(apattern, line)
                    if m:
                        # 排除 URL 中的绝对路径（如 https://example.com/Users/...）
                        if _is_url_ref(line, m.start()):
                            continue
                        problems.append(
                            f"{rel}:{line_no}: 绝对路径 `{m.group(0).rstrip('/')}` → 应使用 ~ 用户级路径"
                        )

    return problems


def do_copy(source: Path, target: Path) -> None:
    """复制 source 目录到 target，先删除已存在的 target。"""
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)


def publish_skill(skill_name: str, repo_root: Path, message: str | None = None, force: bool = False, dry_run: bool = False) -> int:
    """把 products/<skill>/ 发布到 skills-repo/<group>/<skill>/ 并推送到 GitHub。

    返回 0 表示成功，非 0 表示失败。
    """
    source = repo_root / "products" / skill_name
    if not (source / "SKILL.md").is_file():
        print(f"错误：products/{skill_name}/SKILL.md 不存在", file=sys.stderr)
        return RC_PARAM_ERROR

    skills_repo = repo_root / "skills-repo"
    group = resolve_skills_repo_group(skill_name)
    # git 命令以 skills_repo 为 cwd，路径须带分组前缀（顶层分组不带前缀）
    rel_target = f"{group}/{skill_name}" if group else skill_name
    target = skills_repo / rel_target

    # 发布前引用可用性检查：skill 脱离本仓库后，SKILL.md/references 中引用的文件必须随包自带
    problems = check_ref_availability(source)
    if problems:
        print(f"❌ 发布被阻止：{skill_name} 存在仓库外引用（脱离 skills-factory 后不可用）：", file=sys.stderr)
        for p in problems:
            print(f"   - {p}", file=sys.stderr)
        print("", file=sys.stderr)
        print("处理方式（按引用性质）：", file=sys.stderr)
        print("  1. 方法论/参考文档 → 复制到本 skill 的 references/ 目录，并更新引用为 references/<file>", file=sys.stderr)
        print("  2. 仅指路、非功能依赖（如仓库内源文档）→ 加入 ALLOWED_EXTERNAL_REFS 白名单", file=sys.stderr)
        print("  3. 纯文本描述 → 无需处理（检查器不匹配纯文本）", file=sys.stderr)
        return RC_PARAM_ERROR

    if dry_run:
        print(f"[DRY RUN] 将发布 {skill_name}:")
        print(f"  来源: {source}")
        print(f"  目标: {target}")
        print(f"  剥离: tests/ evals/ __pycache__/ *.pyc *.pyo *.bak / test_*.py 等散落测试")
        print(f"  git:  add/commit/push {rel_target} in {skills_repo}")
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
        result = run(["git", "status", "--porcelain", "--", rel_target], cwd=skills_repo, capture=True)
        if not result.stdout.strip():
            print(f"ℹ️  skills-repo/{rel_target} 无变更，无需提交")
            return RC_OK

        run(["git", "add", "--", rel_target], cwd=skills_repo)
        commit_message = message or f"release: {skill_name}"
        run(["git", "commit", "-m", commit_message], cwd=skills_repo)
        run(["git", "push"], cwd=skills_repo)
        print(f"✅ 已发布 {skill_name} 到 skills-repo/{rel_target} 并推送到 GitHub")
        return RC_OK
    except subprocess.CalledProcessError as e:
        print(f"错误：git 操作失败: {e}", file=sys.stderr)
        return RC_GIT_ERROR


def is_published(skill_name: str, repo_root: Path) -> bool:
    """检查 skills-repo/<group>/<skill>/SKILL.md 是否存在（顶层分组无 group 层）。"""
    group = resolve_skills_repo_group(skill_name)
    rel = f"{group}/{skill_name}" if group else skill_name
    return (repo_root / "skills-repo" / rel / "SKILL.md").is_file()


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

    # 分组路径的直接安装（顶层分组无 group 层）：不依赖 skillshare 的递归发现。
    group = resolve_skills_repo_group(skill_name)
    rel_target = f"{group}/{skill_name}" if group else skill_name
    source = f"{remote}/{rel_target}"

    if dry_run:
        print(f"[DRY RUN] 将安装 {skill_name} 到 {target_dir}:")
        print(f"  来源: {source}")
        print(f"  命令:")
        print(f"    skillshare init -p")
        print(f"    skillshare install {source} -p")
        print(f"    skillshare sync -p")
        return RC_OK

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 初始化项目配置（已存在则幂等跳过）
        run(["skillshare", "init", "-p"], cwd=target_dir)

        # 从 GitHub 安装 skill 到项目 source
        install_cmd = ["skillshare", "install", source, "-p"]
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
