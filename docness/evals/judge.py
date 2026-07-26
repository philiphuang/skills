#!/usr/bin/env python3
"""Z.AI-based script judge for skill-up.

Reads agent output from the workspace, calls Z.AI (智谱/OpenAI-compatible)
to evaluate whether the docness task was completed, and prints the
required JSON criterion results.
"""

import json
import os
import sys
import base64
import re
from pathlib import Path
import urllib.request
import urllib.error


def load_text(path: str, max_bytes: int = 4000) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes)
            return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def find_image_files(root: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(p)
    return files


def zai_chat(messages: list[dict], model: str = "glm-4v-flash") -> str:
    api_key = os.environ.get("ZAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
    if not api_key:
        raise RuntimeError("ZAI_API_KEY not set")

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]


def extract_json(text: str) -> list[dict]:
    text = text.strip()
    # Strip markdown fences if present
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        text = m.group(1)
    text = text.strip()
    obj = json.loads(text)
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if "results" in obj:
            return obj["results"]
        # Single criterion object
        return [obj]
    raise ValueError("unexpected JSON type")


def main():
    # Agent context from environment
    exit_code = int(os.environ.get("EVAL_EXIT_CODE", "1") or "1")
    final_message = os.environ.get("EVAL_FINAL_MESSAGE", "")

    # User prompt from agent inputs
    user_prompt = ""
    inputs_file = Path("inputs/messages.json")
    if inputs_file.exists():
        try:
            data = json.loads(inputs_file.read_text())
            msgs = data.get("messages", [])
            if msgs:
                user_prompt = msgs[0].get("content", "")
        except Exception:
            pass

    # Truncate if too long
    user_prompt = user_prompt[:4000]
    final_message = final_message[:8000]

    # Check for generated deliverables
    workspace = Path(".")
    files_note = []
    for d in ["知识库", "发件箱", "收件箱", "工作台"]:
        p = workspace / d
        if p.exists() and p.is_dir():
            children = [x.name for x in p.iterdir() if x.is_file() or x.is_dir()]
            if children:
                files_note.append(f"{d}: {', '.join(children[:10])}")

    # Determine if this is an image generation case
    is_image_task = "配图" in user_prompt or "图片" in user_prompt

    # Build vision messages if image generation and image files exist
    image_attachments = []
    if is_image_task:
        images = find_image_files(workspace)
        if images:
            # Attach the first few images
            for img in images[:3]:
                b64 = base64.b64encode(img.read_bytes()).decode("utf-8")
                ext = img.suffix.lstrip(".").lower()
                if ext == "jpg":
                    ext = "jpeg"
                mime = f"image/{ext}" if ext in {"png", "jpeg", "gif", "webp", "bmp"} else "image/png"
                image_attachments.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })

    content_parts = [
        {"type": "text", "text": f"""You are an expert evaluator for an AI agent skill evaluation. Your job is to decide whether the agent completed the user's docness task.

User prompt: {user_prompt}

Agent exit code: {exit_code}

Agent final message:
{final_message}

Deliverables found in workspace:
{chr(10).join(files_note) if files_note else 'None'}

Return ONLY a JSON object exactly like this example:
{{"results": [{{"criterion": "代理已完成用户请求的 docness 任务，且输出符合预期", "passed": false, "evidence": "The agent final message shows an error and no deliverable was produced."}}]}}

The evidence must cite concrete facts from the agent output. Do not include any markdown, explanation, or keys other than the example shows."""}
    ]
    content_parts.extend(image_attachments)

    messages = [
        {"role": "system", "content": "You are a strict evaluator. Always return ONLY the JSON object format requested by the user, with no extra text."},
        {"role": "user", "content": content_parts}
    ]

    model = "glm-4v" if image_attachments else "glm-4"

    try:
        raw = zai_chat(messages, model=model)
        results = extract_json(raw)
    except Exception as e:
        # Fallback: use a single criterion based on exit code and deliverables
        results = [{
            "criterion": "代理已完成用户请求的 docness 任务，且输出符合预期",
            "passed": exit_code == 0 and len(files_note) > 0,
            "evidence": f"Z.AI judge failed ({e}); using fallback: exit_code={exit_code}, deliverables={len(files_note)}"
        }]

    # Ensure valid shape
    cleaned = []
    for r in results:
        if not isinstance(r, dict):
            continue
        cleaned.append({
            "criterion": str(r.get("criterion", "代理已完成用户请求的 docness 任务")),
            "passed": bool(r.get("passed", False)),
            "evidence": str(r.get("evidence", "")),
        })

    if not cleaned:
        cleaned = [{
            "criterion": "代理已完成用户请求的 docness 任务，且输出符合预期",
            "passed": exit_code == 0 and len(files_note) > 0,
            "evidence": f"No criterion results from LLM; fallback: exit_code={exit_code}, deliverables={len(files_note)}"
        }]

    print(json.dumps(cleaned, ensure_ascii=False))

    # Exit non-zero if any criterion failed
    if any(not r["passed"] for r in cleaned):
        sys.exit(1)


if __name__ == "__main__":
    main()
