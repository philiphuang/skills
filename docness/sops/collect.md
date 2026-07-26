# SOP: 收文件 (Collect)

职责：URL/本地文件 → 获取 → 转 Markdown → 分类保存

## 流程

1. **输入识别** — 运行 `python3 -m scripts.dispatch "<输入>"`（从 docness 目录执行），解析返回 JSON 获得 intent/subtype/source_type
2. **保存原始 URL** — URL 类型的输入先写入 `收件箱/{timestamp}-url.txt`
3. **本地文件** — 复制到 `收件箱/`
4. **格式转换** — 按文件类型调用对应 skill：
   - Word (.docx) → Anthropic `docx` → Markdown
   - Word (.doc) → **先转 .docx**（用 `python3 -c "import subprocess; subprocess.run(['python3', '-m', 'docx2txt', sys.argv[1], sys.argv[2]])"` 或 libreoffice），再读 Markdown
   - PDF → Anthropic `pdf` → Markdown
   - Excel → Anthropic `xlsx` → CSV/Markdown
   - PPT → Anthropic `pptx` → Markdown
   - 腾讯文档 → `tencent-docs` → 导出下载 → 再按类型转换
   - 飞书文档 → `lark-doc`
   - **会议** → `tencent-meeting-mcp` / `lark-minutes` / `lark-vc`
     - 先获取会议主题（subject）和与会人列表（attendees）
     - 构建目录：`知识库/会议纪要/{yymmdd}{主题}/`
     - 文件名：`generate_meeting_filename()` 返回 `(filename, directory)`
     - 示例：`260723-吴鸿涛黄志恒-企业平台沟通-纪要.md` → 目录 `260723企业平台沟通/`
   - 网页 → `baoyu-url-to-markdown`
   - 音视频 → `transcribe`
5. **分类** — 调用 `python3 -m scripts.classify` 判断知识库目录
6. **入库** — 移动到 `知识库/{category}/`，生成规范文件名（这是必须完成的一步，不省略）
7. **记录** — 写 front matter + 更新 index + 写日志

## 转换失败降级

优先 Anthropic skill → 其次 `mineru` → 最后本地提取工具

## 用户交互

- 分类不确定时询问用户
- 处理完成后汇报结果（仅最终结果，不展开中间步骤）

