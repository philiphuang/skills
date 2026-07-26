---
name: docness
description: 文档收发编排器。把 URL/本地文件（Word/PDF/PPT/腾讯文档/飞书/会议录音）自动收进来、转为 Markdown、分类存入知识库；从 Markdown 生成配图/PPT/Word/PDF，或推送到飞书/腾讯文档。触发词：收集、下载、拉取、保存、归档、整理、配图、生成 PPT、转 PDF、转 Word、推送、发送、上传、发布、同步。
version: 1.0.0
metadata:
  mode: production
  platform: opencode
  license: MIT
---

# Docness

把任何来源的文档收进来、转为 AI 可读、再按需交付出去。

## 核心逻辑

```
输入（Word/PDF/腾讯文档/飞书/会议录音）
    ↓ 统一转为
Markdown 知识库（AI 资产底座）
    ↓ 按需输出
配图 / PPT / Word / PDF / 飞书 / 腾讯文档
```

## 三条 SOP

| SOP | 职责 | 典型触发词 |
|-----|------|-----------|
| **收文件** | URL/本地文件 → 获取 → 转 Markdown → 分类保存 | 收集、下载、拉取、保存、归档、整理 |
| **处理** | Markdown → 配图 / 转 Word / 转 PDF / 生成 PPT | 配图、生成 PPT、转 PDF、转 Word |
| **发送** | Markdown/成品 → 上传到飞书/腾讯文档 | 推送、发送、上传、发布、同步 |

## 触发规则

- 裸 URL 或本地路径 → 默认执行 collect SOP
- 带触发词 → 触发词决定 SOP
- Markdown URL/路径 + 无其他意图 → 默认 send 意图

详见 `sops/collect.md`、`sops/process.md`、`sops/send.md`

## 工作区结构

```
收件箱/     → 未分类的原始文件
知识库/     → 已分类 Markdown + docness-index.yml
工作台/     → 处理中的中间产物
发件箱/     → 最终输出
.logs/     → 操作日志（按日期）
```

详见 `references/skill-design.md`

## 脚本入口

| 脚本 | 功能 |
|------|------|
| `scripts/dispatch.py` | 输入识别 + 意图分发 |
| `scripts/classify.py` | 知识库分类（调用大模型） |
| `scripts/state.py` | front matter 读写 + 索引更新 |
| `scripts/index.py` | docness-index.yml 维护 |
| `scripts/utils.py` | 通用工具 |

## 错误处理

- 不确定时先问人，不自作决定
- 保留中间产物，记录错误到 .logs/
- 详见 `references/error-handling.md`

## 依赖 skill

tencent-docs, lark-doc, lark-shared, tencent-meeting-mcp, lark-minutes, lark-vc,
baoyu-url-to-markdown, baoyu-image-gen, baoyu-slide-deck,
md2feishu, transcribe, Anthropic docx/pdf/pptx/xlsx, mineru
