"""Playwright 浏览器通道：千问逐字稿导出（#217 迁移，替代 ego-browser）。

与 ego-browser 的差异：
- 导航：直 URL 会被 SPA 路由弹回首页，需先从首页侧边栏点击进入会话
- 驱动：ego-browser taskSpace/page API → playwright 原生 API
- 页面交互逻辑（选择器、导出流程）与 ego-browser 版完全一致

Cookie 通过 playwright context.add_cookies 注入，来源与 api.py 一致。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_OTHER = 1
EXIT_LOGIN_EXPIRED = 2
EXIT_NOT_FOUND = 3
EXIT_NO_EXPORT = 4

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _parse_cookie_string(cookie_raw: str) -> list[dict]:
    """Raw cookie header string → playwright cookie list."""
    cookies = []
    for pair in cookie_raw.split("; "):
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".qianwen.com",
            "path": "/",
        })
    return cookies


async def fetch_transcript(conversation_id: str, out_path: str, cookie_raw: str,
                           timeout_s: int = 90) -> dict:
    """开浏览器导出指定会话的逐字稿 txt。返回与 ego-browser 版相同的 result dict。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "code": EXIT_OTHER, "error": "playwright 未安装"}

    cookies = _parse_cookie_string(cookie_raw)
    if not cookies:
        return {"ok": False, "code": EXIT_LOGIN_EXPIRED, "error": "Cookie 为空"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(
            user_agent=USER_AGENT,
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        try:
            # 1. 首页 → 侧边栏点击进入会话（直 URL 会被 SPA 弹回首页）
            await page.goto("https://www.qianwen.com/", wait_until="domcontentloaded",
                            timeout=timeout_s * 1000)
            await page.wait_for_timeout(8000)

            # 检查登录态
            body = await page.inner_text("body")
            if "登录" in body and "最近对话" not in body:
                return {"ok": False, "code": EXIT_LOGIN_EXPIRED, "error": "检测到登录墙"}

            # 侧边栏点击目标会话（playwright locator 点击 — page.evaluate 不触发 SPA 路由）
            try:
                # 优先按 conversation_id 匹配 href
                href_loc = page.locator(f'a[href*="{conversation_id}"]')
                if await href_loc.count() > 0:
                    await href_loc.first.click()
                else:
                    # fallback：点击第一个录音纪要会话
                    await page.locator("text=录音纪要：").first.click()
            except Exception as e:
                return {"ok": False, "code": EXIT_NOT_FOUND,
                        "error": f"侧边栏点击失败: {e}"}
            await page.wait_for_timeout(8000)

            # 验证进入了目标会话（侧边栏点击可能导航到完整 ID 的 URL）
            if conversation_id not in page.url:
                return {"ok": False, "code": EXIT_NOT_FOUND,
                        "error": f"未进入目标会话，当前 URL: {page.url}"}
            body = await page.inner_text("body")
            if "对话不存在" in body:
                return {"ok": False, "code": EXIT_NOT_FOUND,
                        "error": f"对话不存在: {conversation_id}"}

            has_minutes = ("帮我总结录音内容" in body or "录音纪要：" in body)
            if not has_minutes:
                return {"ok": False, "code": EXIT_NOT_FOUND,
                        "error": "会话存在但非录音会话"}

            # 2. 打开纪要面板（等「创建于」出现，说明纪要卡片已渲染）
            try:
                await page.wait_for_selector("text=创建于", timeout=15000)
                await page.click("text=创建于", timeout=5000)
                await page.wait_for_timeout(3000)
            except Exception as e:
                return {"ok": False, "code": EXIT_NO_EXPORT,
                        "error": f"纪要面板未能打开: {e}"}

            # 3. 点击导出与分享
            clicked_export = await page.evaluate("""() => {
                for (const b of document.querySelectorAll('button,[role=button]')) {
                    if (b.offsetParent === null) continue;
                    if ((b.getAttribute('aria-label') || '').trim() === '导出与分享') {
                        b.click(); return 'aria';
                    }
                }
                for (const el of document.querySelectorAll('button,[role=button],div,span')) {
                    if (el.offsetParent === null || el.tagName === 'SPAN') continue;
                    if ((el.textContent || '').trim() === '导出与分享') {
                        el.click(); return 'text';
                    }
                }
                return null;
            }""")
            if not clicked_export:
                return {"ok": False, "code": EXIT_NO_EXPORT, "error": "未找到导出与分享按钮"}
            await page.wait_for_timeout(2000)

            # 4. 原文区块格式切 txt
            cur_fmt = await page.evaluate("""() => {
                const FMT = /^(pdf|txt|docx)$/i;
                for (const el of document.querySelectorAll('span')) {
                    const own = Array.from(el.childNodes)
                        .filter(n => n.nodeType === 3)
                        .map(n => n.textContent.trim()).join('');
                    if (!FMT.test(own)) continue;
                    let p = el.parentElement, sect = null;
                    while (p && p !== document.body) {
                        const t = p.innerText || '';
                        if (/原文/.test(t) && !/纪要/.test(t)) { sect = '原文'; break; }
                        if (/纪要/.test(t) && !/原文/.test(t)) { sect = '纪要'; break; }
                        p = p.parentElement;
                    }
                    if (sect === '原文') { el.click(); return own.toLowerCase(); }
                }
                return null;
            }""")
            if not cur_fmt:
                return {"ok": False, "code": EXIT_NO_EXPORT,
                        "error": "导出弹窗原文区块无格式下拉"}
            await page.wait_for_timeout(1500)

            if cur_fmt != "txt":
                picked = await page.evaluate("""() => {
                    for (const el of document.querySelectorAll('div')) {
                        if (!/selectOption/.test(el.className || '')) continue;
                        const own = Array.from(el.childNodes)
                            .filter(n => n.nodeType === 3)
                            .map(n => n.textContent.trim()).join('');
                        if (own === 'txt' && el.offsetParent !== null) {
                            el.click(); return true;
                        }
                    }
                    return false;
                }""")
                if not picked:
                    return {"ok": False, "code": EXIT_NO_EXPORT,
                            "error": "格式下拉无 txt 选项"}
                await page.wait_for_timeout(1000)

            # 5. 点导出按钮，等下载
            download_promise = page.wait_for_event("download", timeout=20000)
            confirmed = await page.evaluate("""() => {
                const b = document.querySelector('[class*="exportBtn"]');
                if (!b || b.offsetParent === null) return false;
                b.click(); return true;
            }""")
            if not confirmed:
                return {"ok": False, "code": EXIT_NO_EXPORT,
                        "error": "导出确认按钮不可见"}

            download = await download_promise
            fname = download.suggested_filename or ""
            title = fname.replace("原文_", "").rsplit(".", 1)[0] if fname else ""
            await download.save_as(out_path)
            return {"ok": True, "path": out_path, "title": title.strip()}

        except Exception as e:
            return {"ok": False, "code": EXIT_OTHER, "error": f"浏览器执行异常: {e}"}
        finally:
            await browser.close()


def run_fetch(conversation_id: str, out_path: Path, cookie_raw: str,
              timeout_s: int = 90) -> dict:
    """同步入口（供 getter.py 调用）。"""
    return asyncio.run(
        fetch_transcript(conversation_id, str(out_path.resolve()), cookie_raw, timeout_s)
    )
