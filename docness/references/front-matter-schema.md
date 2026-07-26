# Front Matter Schema

```yaml
docness:
  source: "https://docs.qq.com/..."          # 原始来源 URL
  source_type: "tencent-docs"                # 来源类型
  imported_at: "2026-07-19T10:00:00+08:00"   # 收集时间
  knowledge_category: "会议纪要"              # 知识库分类
  original_filename: "foo.docx"              # 原始文件名
  status: "collected"                        # collected | processed | published
  processing:                                 # 处理记录
    - action: "illustrate"
      skill: "baoyu-image-gen"
      outputs:
        - "发件箱/xxx.md"
      processed_at: "2026-07-19T11:00:00+08:00"
  published:                                  # 发送记录
    - target: "feishu"
      doc_token: "..."
      url: "https://..."
      published_at: "2026-07-19T12:00:00+08:00"
```

## Status 语义

- `collected`: 已获取并保存到知识库
- `processed`: 已调用处理 skill，成品已放入 发件箱/
- `published`: 已推送到飞书/腾讯文档
- status 取当前最高状态（一个文件可以同时是 processed + published）
