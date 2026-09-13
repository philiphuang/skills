# SOP: 发送 (Send)

职责：Markdown/成品 → 上传到飞书/腾讯文档

## 前置条件：解析工作区

开始前先运行 `python3 -m scripts.init_workspace "<项目根目录>"` 解析项目级工作区（详见 SKILL.md「前置条件与初始化」）。
本文 `发件箱/` 等路径一律指输出 JSON 中 `workspace` 的**绝对路径**，严禁落到 skill 自身目录。

## 触发方式

- 用户直接给 Markdown URL/路径（默认 send 意图）
- `/docness send <文件路径> <目标>`
- 自然语言触发词见 `scripts/dispatch.py:SEND_TRIGGERS`

## 目标判断

1. 读取 Markdown front matter
2. 若已指定目标（`feishu-doc` / `tencent-doc`）→ 直接推送
3. 若未指定 → 询问用户选择飞书/腾讯文档

## 调用 skill

| 目标 | skill |
|------|-------|
| 飞书文档/wiki | `md2feishu` |
| 腾讯文档 | `tencent-docs` |

## 记录

调用 `record_publish(filepath, target, doc_token, url)` 写入 front matter。完成判据：front matter 的 `published` 数组已追加本次记录（含 target/doc_token/url/published_at），且 status 已更新为 `published`。
