"""v2 纯获取能力（getter，#202/#205/#206）：list-new 增量列会话 + fetch 浏览器导出原文 txt。

零存储零分类零调度：list-new 只推游标吐 JSONL；fetch 只产出官方导出的原文 txt。
存储/结构/分类由调用方（docness collect 等）承担。

fetch 浏览器通道：
- Mac：ego-browser（保留，向后兼容）
- Linux/oyun：playwright + chromium 无头（#217 迁移）
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .api import ApiError, QianwenClient, load_cookie
from .state import load as state_load, mark_done, save as state_save, select_increment, unmark

EXIT_OK = 0
EXIT_OTHER = 1
EXIT_LOGIN_EXPIRED = 2
EXIT_NOT_FOUND = 3
EXIT_NO_EXPORT = 4

CHAT_URL_RE = re.compile(r"qianwen\.com/chat/([0-9a-fA-F]{16,})")
DEFAULT_STATE = Path("/opt/prjs/2606国际公司MCloud/.scratch/qianwen-minutes-sync/state.json")


def parse_conversation_ref(ref: str) -> str:
    """会话 ID 或 chat URL → 纯 ID。"""
    ref = (ref or "").strip()
    m = CHAT_URL_RE.search(ref)
    if m:
        return m.group(1)
    if re.fullmatch(r"[0-9a-fA-F]{16,}", ref):
        return ref
    raise ValueError(f"无法解析会话标识: {ref}")


def _has_ego_browser() -> bool:
    return shutil.which("ego-browser") is not None


def _has_playwright() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


# ego-browser 脚本：开会话页 → 开纪要面板 → 导出与分享 → 原文 txt → saveAs。
# -e 按普通脚本执行（非模块），顶层 await/return 非法，故整体包 async IIFE。
# RESULT 行是唯一的机器可读输出，Python 侧据此映射退出码。
_BROWSER_JS = r"""
(async () => {
const OUT = __OUT__;
const CID = "__CID__";
// 遗留清理：上次运行若中途死掉，空间停在交接态，会让本轮 taskSpace 全部暂停。
// 只收拾自家命名（qianwen-fetch*/qf-*）的非 agent 态空间；他人空间不碰。
for (const s of await listTaskSpaces()) {
  if (!/^(qianwen-fetch|qf-)/.test(s.name)) continue;
  if (s.ownership === "agent") continue;
  try { const t = await takeOverTaskSpace(s.id); await t.finish({ keep: [] }); } catch (e) {}
}
const task = await taskSpace("qianwen-fetch");
const page = task.page("p1");
const fail = async (code, msg) => {
  console.log("RESULT: " + JSON.stringify({ ok: false, code, error: msg }));
  try { await task.finish({ keep: [] }); } catch (e) {}
};
await page.goto("https://www.qianwen.com/chat/" + CID + "?entry=audio_qianwen");
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(3000);

const url = await page.url();
if (/login|passport/i.test(url)) { await fail(2, "登录页跳转: " + url); return; }

// 会话存在性：录音会话页必含「帮我总结录音内容」触发气泡或纪要卡片
const hasConv = await page.evaluate(() =>
  document.body.innerText.includes("帮我总结录音内容") ||
  document.body.innerText.includes("录音纪要："));
if (!hasConv) { await fail(3, "会话不存在或非录音会话: " + url); return; }

// 登录态特征：未登录时侧边栏是「登录」入口而非账号名
const loginWall = await page.evaluate(() => {
  const t = document.body.innerText;
  return /登录|扫码/.test(t) && !t.includes("最近对话");
});
if (loginWall) { await fail(2, "检测到登录墙"); return; }

// 开纪要面板：点卡片上的「创建于 …」行（每页唯一）
try {
  await page.click('text=创建于', { label: "open minutes panel" });
  await page.waitForSelector('loc=role:tab[name="转写"]', { timeout: 15000 });
} catch (e) { await fail(4, "纪要面板未能打开: " + e); return; }
await page.waitForTimeout(1000);

// 导出与分享 → 原文格式切 txt → 导出 → 前端本地 Blob 下载。
// 弹窗无 role=dialog，格式下拉按「原文区块」（祖先文本含原文不含纪要）锚定；
// 确认按钮只能按 class 取——按文本「导出」会先撞上同名的弹窗 tab。
const openFormatDropdown = () => page.evaluate(() => {
  const FMT = /^(pdf|txt|docx)$/i;
  for (const el of document.querySelectorAll("span")) {
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join("");
    if (!FMT.test(own)) continue;
    let p = el.parentElement, sect = null;
    while (p && p !== document.body) {
      const t = p.innerText || "";
      if (/原文/.test(t) && !/纪要/.test(t)) { sect = "原文"; break; }
      if (/纪要/.test(t) && !/原文/.test(t)) { sect = "纪要"; break; }
      p = p.parentElement;
    }
    if (sect === "原文") { el.click(); return own.toLowerCase(); }
  }
  return null;
});
let title = "";
try {
  // 面板窄时头部按钮收成纯图标：文本 SPAN display:none（0×0），text= 会命中它而报
  // zero-sized bounding box——改点可见按钮本体（aria-label 锚定，textContent 兜底）。
  const openedDialog = await page.evaluate(() => {
    for (const b of document.querySelectorAll("button,[role=button]")) {
      if (b.offsetParent === null) continue;
      if ((b.getAttribute("aria-label") || "").trim() === "导出与分享") { b.click(); return "aria"; }
    }
    for (const el of document.querySelectorAll("button,[role=button],div,span")) {
      if (el.offsetParent === null || el.tagName === "SPAN") continue;
      if ((el.textContent || "").trim() === "导出与分享") { el.click(); return "text"; }
    }
    return null;
  });
  if (openedDialog === null) { await fail(4, "未找到可见的导出与分享按钮"); return; }
  await page.waitForTimeout(2000);
  const cur = await openFormatDropdown();
  if (cur === null) { await fail(4, "导出弹窗原文区块无格式下拉"); return; }
  await page.waitForTimeout(1000);
  const picked = await page.evaluate(() => {
    for (const el of document.querySelectorAll("div")) {
      if (!/selectOption/.test(el.className || "")) continue;
      const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join("");
      if (own === "txt" && el.offsetParent !== null) { el.click(); return true; }
    }
    return false;
  });
  if (!picked) { await fail(4, "格式下拉无 txt 选项"); return; }
  await page.waitForTimeout(1000);
  const downloadPromise = page.waitForEvent("download", { timeout: 20000 });
  const confirmed = await page.evaluate(() => {
    const b = document.querySelector('[class*="exportBtn"]');
    if (!b || b.offsetParent === null) return false;
    b.click(); return true;
  });
  if (!confirmed) { await fail(4, "导出确认按钮不可见"); return; }
  const download = await downloadPromise.catch(() => null);
  if (!download) { await fail(4, "下载未触发"); return; }
  // 标题取自官方导出文件名（原文_<标题>.txt）——全页正则会撞侧边栏「最近对话」
  const fname = await download.suggestedFilename();
  title = fname.replace(/^原文_/, "").replace(/\.txt$/i, "");
  await download.saveAs(OUT);
} catch (e) { await fail(4, "导出流程失败: " + e); return; }
console.log("RESULT: " + JSON.stringify({ ok: true, path: OUT, title: title.trim() }));
try { await task.finish({ keep: [] }); } catch (e) {}
})();
"""


def _run_browser(conversation_id: str, out_path: Path, timeout_s: int,
                 cookie: str = "") -> dict:
    """浏览器通道分发：playwright 优先（Linux/oyun），ego-browser 兜底（Mac）。"""
    if _has_playwright():
        from .playwright_fetch import run_fetch
        return run_fetch(conversation_id, out_path, cookie, timeout_s)
    return _run_ego_browser(conversation_id, out_path, timeout_s)


def _run_ego_browser(conversation_id: str, out_path: Path, timeout_s: int) -> dict:
    """跑 ego-browser 脚本，解析 RESULT 行。"""
    js = _BROWSER_JS.replace("__OUT__", json.dumps(str(out_path.resolve()))).replace("__CID__", conversation_id)
    try:
        proc = subprocess.run(
            ["ego-browser", "nodejs", "-e", js],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except FileNotFoundError:
        return {"ok": False, "code": EXIT_OTHER, "error": "ego-browser 未安装或不在 PATH（且无 playwright）"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": EXIT_OTHER, "error": f"浏览器执行超时（{timeout_s}s）"}

    # ego-browser 的 console 输出可能走 stderr，两边都扫，stdout 优先
    for stream in (proc.stdout or "", proc.stderr or ""):
        for line in stream.splitlines():
            if line.startswith("RESULT: "):
                try:
                    return json.loads(line[len("RESULT: "):])
                except json.JSONDecodeError:
                    continue
    tail = ((proc.stderr or "") + (proc.stdout or ""))[-500:]
    return {"ok": False, "code": EXIT_OTHER, "error": f"浏览器无结果输出。{tail}"}


def cmd_list_new(args: argparse.Namespace) -> int:
    """增量列出新增录音会话（JSONL）；输出即推游标。"""
    try:
        client = QianwenClient(load_cookie(args.cookie, Path(args.cookie_file).expanduser() if args.cookie_file else None))
        client.probe()
    except ApiError as exc:
        print(json.dumps({"ok": False, "error": f"Cookie 失效或网络异常: {exc}"}, ensure_ascii=False))
        return EXIT_LOGIN_EXPIRED

    state_path = Path(args.state).expanduser() if args.state else DEFAULT_STATE
    state = {"conversations": {}} if args.reset else state_load(state_path)
    conversations = client.audio_conversations()
    fresh = conversations if args.reset else select_increment(state, conversations)

    for conv in fresh:
        print(json.dumps({k: conv.get(k) for k in ("id", "title", "create_time", "updated_at")},
                         ensure_ascii=False))
    for conv in fresh:
        state = mark_done(state, conv, "list-new")
    state_save(state_path, state)
    return EXIT_OK


def cmd_fetch(args: argparse.Namespace) -> int:
    """导出指定会话的官方原文 txt（浏览器通道）。"""
    try:
        conversation_id = parse_conversation_ref(args.conversation)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return EXIT_OTHER

    # Cookie 只在 playwright 通道需要（ego-browser 自带登录态）
    cookie = ""
    if _has_playwright():
        try:
            cookie = load_cookie(args.cookie, Path(args.cookie_file).expanduser() if args.cookie_file else None)
        except ApiError as exc:
            print(json.dumps({"ok": False, "error": f"Cookie 加载失败: {exc}"}, ensure_ascii=False))
            return EXIT_LOGIN_EXPIRED

    out_path = Path(args.out).expanduser() if args.out else Path(f"qianwen-transcript-{conversation_id[:12]}.txt")
    result = _run_browser(conversation_id, out_path, args.timeout, cookie=cookie)

    # fetch 失败 → 回滚 state 游标，下次 list-new 会重新吐出该会话
    if not result.get("ok"):
        state_path = Path(args.state).expanduser() if args.state else DEFAULT_STATE
        st = state_load(state_path)
        st = unmark(st, conversation_id)
        state_save(state_path, st)

    payload = {"conversation_id": conversation_id, "path": str(out_path)}
    payload.update({k: v for k, v in result.items() if k in ("ok", "error", "title")})
    if result.get("ok") and out_path.exists():
        payload["bytes"] = out_path.stat().st_size
    print(json.dumps(payload, ensure_ascii=False))
    return result.get("code", EXIT_OTHER) if not result.get("ok") else EXIT_OK
