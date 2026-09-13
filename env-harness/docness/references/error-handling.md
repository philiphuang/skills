# Error Handling

## 核心原则

- 置信度低或不确定时，先问人，不自作决定
- 保留中间产物，记录错误到 `.logs/`，方便排查和重试

## 常见错误

| 场景 | 处理 |
|---|---|
| URL 无法识别 | 停止，列出已知来源，询问用户 |
| 所需 skill 未安装 | 停止，提示用户通过 skillshare 安装 |
| skill 调用失败 | 保留中间产物，记录错误到 `.logs/`，提示重试 |
| 分类不确定 | 询问用户，由用户决定分类或新建目录 |
| 发送目标未指定 | 询问用户选择飞书/腾讯文档 |
| 覆盖风险 | 目标文档已有内容 → 警告并确认后再推送 |
| 腾讯文档/飞书认证过期 | 静默执行重新授权（不询问用户）。能打开浏览器则自动打开；否则返回授权链接让用户点击。授权链接必须单独成行，避免多余符号被一并点击。 |
| **simple 管道转换失败** | `convert_to_markdown` 自动升级到 complex 路由（MinerU）；不支持的文件类型不升级，直接报错。详见 collect.md「转换失败降级」 |
| **LibreOffice 不可用** | 提示用户手动将旧格式(.doc/.ppt/.xls)另存为新格式(.docx/.pptx/.xlsx)，或安装 LibreOffice |
| **复杂度判定超阈值** | 静默路由到 MinerU，不打断用户。最终结果中注明使用了 MinerU |
| **MinerU 转换失败** | 降级到 Anthropic docx/pdf/pptx/xlsx Skill 作最后一层兜底，保留中间产物 |

## 日志格式

```
# Docness 操作日志 YYYY-MM-DD

## 操作 N
- 时间：HH:MM
- 文件：收件箱/xxx
- 来源：https://...
- 类型：xxx
- 执行动作：xxx
- 输出：xxx
- 状态：已完成/失败
```

日志文件路径：`.logs/YYYY-MM-DD-docness.md`
