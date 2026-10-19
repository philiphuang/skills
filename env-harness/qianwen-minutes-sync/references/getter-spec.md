# v2 纯获取规范（#205 锁定 / #206 实现，2026-10-15）

本文件是 qianwen-minutes-sync **v2 getter**（`list-new` / `fetch`）的规范唯一事实源。
定形决策见 issue #205（grilling 锁定）、实现见 #206；上游地图 #202；前置研究 #203（浏览器通道唯一性证明）。
v1 管线（run/finalize，归档/分类/调度）转遗留，规范仍见 `archive-spec.md` / `classification-spec.md` / `run-spec.md`。

## 1. 职责边界（零存储零分类零调度）

- skill 只做**获取**：列出新会话、导出官方原文 txt，两个子命令各自完整可独立手跑
- **不做**存储落位、分类判定、定时调度——全部由调用方承担（当前唯一编排消费方：docness collect，见其 `sops/collect.md` 4c 千问分支）
- **agent 中立**：不绑定任何特定 agent/自动化载体；编排如何跑是调用方的事，skill 定义不含编排

## 2. list-new：增量列会话

- **通道**：`chat2-api.qianwen.com` 会话列表 API，**Cookie 快照**鉴权（该域只验 Cookie，#203 实测）；
  Cookie 优先级 `--cookie` > 环境变量 `QIANWEN_COOKIE` > 快照文件（默认 `~/.config/project-daimon/qianwen-cookie.txt`）
- **输出**：JSONL，每行 `{id, title, create_time, updated_at}`；**输出即推游标**——打印完成即写 state.json，无确认步骤
- **游标**：`--state` 指定路径（默认 `/opt/prjs/2606国际公司MCloud/.scratch/qianwen-minutes-sync/state.json`，与 v1 共用）；
  判定增量复用 state.py：不在游标或 `updated_at` 变化
- **`--reset`**：忽略游标吐全量（历史回填入口），随后照常写游标
  （全量回填的组合用法：`list-new --reset` 列出全部 → 串行逐个 `fetch`，一次浏览器会话一个文件）
- **退出码**：0 成功；2 Cookie 失效/网络异常（输出一行错误 JSON）

## 3. fetch：导出官方原文 txt

- **通道**：**浏览器（ego-browser）登录态**。唯一可行通道：转写正文与音频接口都在
  `ai-note.qianwen.com` AWSC 验签墙后（D0001，Cookie 不参与放行），纯脚本直调不可达（#203 三方交叉验证）；
  txt 导出本身是前端 `new Blob()` 本地生成，无网络接口
- **命令**：在 `scripts/` 目录下 `python3 -m qianwen_sync.run fetch <会话ID或chat URL> [--out 路径] [--timeout 秒]`
- **产出**：官方导出原文 txt，`[mm:ss] 发言人N: 文本` 逐段、段间空行；默认落当前目录 `qianwen-transcript-<ID12>.txt`
- **退出码（语义化，供调用方分支）**：
  | 码 | 含义 | 调用方处置 |
  |----|------|------------|
  | 0 | 成功（输出 JSON 含 path/bytes/title） | 收文件 |
  | 1 | 其他错误（ref 非法 / ego-browser 未装 / 无结果输出 / 超时） | 看错误行排查 |
  | 2 | 登录失效（登录页跳转/登录墙） | 提示人工重新登录 ego-browser |
  | 3 | 会话不存在或非录音会话 | 跳过并记录 |
  | 4 | 无导出入口（面板/按钮/下载未触发） | 站点改版嫌疑，人工看页面 |
- **运行纪律**：单会话一次浏览器会话，默认 90s 超时，**失败不自动重试**（串行逐个 fetch 由调用方控制）
- **凭证**：与 list-new 双通道分离——fetch 只依赖 ego-browser 已登录千问（人工登录态），不读 Cookie 快照

## 4. 与 docness 的接口

- fetch 产出的 txt 由 docness collect 入库：category 固定 `会议纪要`、source=chat URL、
  `source_type: qianwen-audio`、original_filename=导出 txt 文件名（见 docness `references/front-matter-schema.md`）
- **所有文件重新获取**（#205 锁定）：历史会话一律重 fetch 官方导出，不复用 v1 归档的 AI 纪要
- AI 纪要、音频 mp3 均不在 v2 产出范围（#205 锁定：逐字稿为唯一对象）

## 5. 站点结构备忘（#206 实测，2026-10-15）

- 导出弹窗**无 `role=dialog`**；弹窗内「导出 / 分享」是两个 tab，文本选「导出」会先撞 tab 而非确认按钮
- 弹窗分「原文 / 纪要」两组，各带格式下拉（txt/docx/pdf）。**原文区块锚定法**：
  取格式 span，向上找 innerText 含「原文」不含「纪要」的祖先
- 确认按钮按 class `exportBtn` 取；txt 是前端 `new Blob()` 本地生成，点击后即触发 download 事件
- **导出文件名即权威标题**（`原文_<标题>.txt`）——从 `download.suggestedFilename()` 提取；
  不要从页面正则取「录音纪要：」，会撞侧边栏「最近对话」
- **导出与分享入口锚定（2026-10-18 修订，#206 修复）**：面板窄时头部按钮收成纯图标——
  文本 SPAN（`headerActionText-*`）`display:none`（0×0），`text=导出与分享` 命中的就是它，
  报 zero-sized bounding box（10-16 两会话实测）。**不要用文本选择器**，改点可见按钮本体：
  `button` 且 `offsetParent !== null` 且 `aria-label="导出与分享"`（textContent 兜底）
- **遗留交接态空间会卡死后续运行**（2026-10-18 实测）：上次运行中途死掉后任务空间停在
  `agentDelegatedToUser`，之后每次 `taskSpace()` 都被浏览器暂停（等用户收回）。脚本开头须
  `listTaskSpaces()` 清理自家命名（`qianwen-fetch*`/`qf-*`）的非 agent 态空间
  （`takeOverTaskSpace(id)` + `finish({keep:[]})`）再开跑；他人空间不碰
