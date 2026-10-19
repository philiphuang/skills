"""qianwen.com web API 客户端（2026-09-27 改版后实测形状；Cookie 快照鉴权，#107/#111）。

改版要点（旧 /api/v1/conversations 已全域 404）：
- 会话列表与轮次迁至 chat2-api.qianwen.com，端点 /api/v1/session/list、/api/v1/session/msg/list；
- 列表项无 entry 字段，录音会话以标题前缀辨识（50 条样本实测）；
- 纪要正文接口（ai-note.qianwen.com）有验签墙（阿里 AWSC，D0001），纯脚本不可达；
  v1 只落存根：msg/list 轮次里的 minutes_id/note_id/duration 入 front-matter，正文走直达链接。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://chat2-api.qianwen.com"
DEFAULT_COOKIE_FILE = Path.home() / ".config" / "project-daimon" / "qianwen-cookie.txt"
AUDIO_ENTRY = "audio_qianwen"
AUDIO_TITLE_PREFIXES = ("录音纪要：", "总结录音内容")  # 实测仅有的两种录音标题形态（含未命名默认题）
PAGE_SIZE = 50
MAX_PAGES = 20
# 公共查询参数实测必需；ut 为设备指纹 UUID（缺失即 400 {"code":10001,"msg":"ut"}），
# 来源=首次导出 Cookie 快照的浏览器设备。
COMMON_PARAMS = (
    "biz_id=ai_qwen&chat_client=h5&device=pc&fr=h5&pr=qwen"
    "&ut=7447be63-5bc3-9a42-ea83-34d35b198deb&la=zh-CN&tz=Asia%2FSingapore"
    "&wv=4.9.1&tq=SD&ve=4.9.1"
)


class ApiError(RuntimeError):
    """探活/请求失败。Cookie 失效与网络异常统一由此表达，run 层报告后终止。"""


def load_cookie(explicit: str | None = None, cookie_file: Path | None = None) -> str:
    """Cookie 来源优先级：参数 > 显式指定的快照文件 > 环境变量 QIANWEN_COOKIE > 默认快照文件。"""
    if explicit:
        return explicit.strip()
    if cookie_file is not None:
        text = cookie_file.read_text(encoding="utf-8").strip() if cookie_file.exists() else ""
        if not text:
            raise ApiError(f"Cookie 快照文件为空或不存在: {cookie_file}")
        return text
    env = os.environ.get("QIANWEN_COOKIE", "").strip()
    if env:
        return env
    path = cookie_file or DEFAULT_COOKIE_FILE
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    raise ApiError(f"缺少 Cookie：设置 QIANWEN_COOKIE 环境变量，或写入快照文件 {path}（单行原始 Cookie 头）")


def is_audio_title(title: str) -> bool:
    return any(title.startswith(p) for p in AUDIO_TITLE_PREFIXES)


def _normalize_session(item: dict) -> dict | None:
    """session/list 项 → 下游（state/archive/run）约定的 conv 形状；非录音标题由调用方过滤。"""
    sid = str(item.get("session_id") or "")
    if not sid:
        return None
    return {
        "id": sid,
        "title": item.get("title") or "",
        "create_time": item.get("create_time"),  # ISO 字符串
        "updated_at": item.get("updated_at"),    # epoch 毫秒，游标增量比较用
        "entry": AUDIO_ENTRY,
    }


def _extract_minutes_meta(turn: dict) -> dict:
    """轮次 → 纪要元数据。biz_data（JSON 字符串）有 duration/minutes_id/note_id，
    multi_load content 另有纪要卡片自报标题与状态。"""
    biz: dict = {}
    raw = turn.get("biz_data")
    if isinstance(raw, str):
        try:
            biz = json.loads(raw)
        except json.JSONDecodeError:
            biz = {}
    elif isinstance(raw, dict):
        biz = raw
    meta = {k: biz[k] for k in ("minutes_id", "note_id", "duration") if biz.get(k) is not None}
    for msg in turn.get("response_messages") or []:
        if not isinstance(msg, dict):
            continue
        for load in (msg.get("meta_data") or {}).get("multi_load") or []:
            content = load.get("content") if isinstance(load, dict) else None
            if not isinstance(content, dict) or not content.get("minutes_id"):
                continue
            meta.setdefault("minutes_id", content["minutes_id"])
            if content.get("note_id"):
                meta.setdefault("note_id", content["note_id"])
            if content.get("title"):
                meta["minutes_title"] = content["title"]
            if content.get("status"):
                meta["minutes_status"] = content["status"]
            if content.get("finished_at"):
                meta["finished_at"] = content["finished_at"]
            return meta
    return meta


class QianwenClient:
    def __init__(self, cookie: str, base: str = BASE):
        self.cookie = cookie
        self.base = base.rstrip("/")

    def _get(self, path: str) -> object:
        req = urllib.request.Request(
            self.base + path,
            headers={
                "Cookie": self.cookie,
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ApiError(f"HTTP {exc.code}: {path}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ApiError(f"请求失败: {path}: {exc}") from exc

    def sessions(self, page: int = 1, page_size: int = PAGE_SIZE) -> dict:
        doc = self._get(
            f"/api/v1/session/list?page={page}&page_size={page_size}"
            f"&return_response_messages=false&{COMMON_PARAMS}"
        )
        return doc if isinstance(doc, dict) else {}

    def audio_conversations(self) -> list[dict]:
        """全量翻页取录音纪要会话；翻页终止=have_next_page（改版后无 total 字段）。"""
        out: list[dict] = []
        page = 1
        while page <= MAX_PAGES:
            data = self.sessions(page=page).get("data") or {}
            items = data.get("list") or []
            for item in items:
                if isinstance(item, dict) and is_audio_title(str(item.get("title") or "")):
                    norm = _normalize_session(item)
                    if norm is not None:
                        out.append(norm)
            if not items or not data.get("have_next_page"):
                break
            page += 1
        return out

    def minutes_meta(self, session_id: str) -> dict:
        """msg/list 轮次中提取纪要元数据（按轮次新旧序首个命中）。"""
        doc = self._get(f"/api/v1/session/msg/list?session_id={session_id}&page_size=20&{COMMON_PARAMS}")
        turns = (doc.get("data") or {}).get("list") if isinstance(doc, dict) else None
        for turn in turns or []:
            if isinstance(turn, dict):
                meta = _extract_minutes_meta(turn)
                if meta:
                    return meta
        return {}

    def messages(self, conversation_id: str) -> list[dict]:
        """v1 存根载体：返回合成 minutes_meta 消息（摘要/转写正文被验签墙挡住，不可得）。"""
        meta = self.minutes_meta(conversation_id)
        return [{"type": "minutes_meta", "meta": meta}] if meta else []

    def probe(self) -> None:
        """探活（#110 §4）：session/list 首页 code=0 且 data.list 为列表即 Cookie 有效。"""
        doc = self.sessions(page=1, page_size=1)
        data = doc.get("data") or {}
        if doc.get("code") != 0 or not isinstance(data.get("list"), list):
            raise ApiError(
                f"探活失败：session/list 响应形状异常 code={doc.get('code')} msg={doc.get('msg')}"
                "（疑似 Cookie 失效或接口改版）"
            )
