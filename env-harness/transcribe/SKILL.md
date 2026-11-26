---
name: transcribe
description: 将视频/音频文件自动转写为带时间戳分段的会议纪要 Markdown 逐字稿。支持 mp4/mp3/wav/m4a/flac 等格式，自动调用 ffmpeg 提取音轨，默认先做静音扫描与分段裁剪（长静音不付费不重传）再上传 DashScope，逐字稿时间戳自动映射回原片时间，适合长录音乃至全天录音（实测 2h+）。--diarize 开启说话人分离（paraformer-v2，实测 6 人），默认模型输出「片段N」分段。
license: MIT
metadata:
  version: "1.2.1"
  mode: production
  platform: opencode
---

# transcribe

将会议录音或录屏自动转写成带时间戳分段的 Markdown 逐字稿（说话人标注能力取决于所用 ASR 模型）。

## 使用方法

```
/transcribe <输入文件路径> [--output-dir <输出目录>]
```

### 实际调用方式

本 Skill 通过 Python 脚本执行：

```bash
python scripts/transcribe.py <输入文件路径> [--output-dir <输出目录>]
```

## 音频格式说明

- **支持输入**：mp4, mp3, wav, m4a, flac, avi, mkv, mov 等常见音频/视频格式
- **内部处理**：自动通过 ffmpeg 转码为 WAV pcm_s16le, 16000Hz, 单声道后上传
- **推荐格式**：任意格式均可，脚本会自动处理兼容性

## 输出目录推导

按以下优先级确定输出目录：

1. **用户显式指定** `--output-dir`
2. **项目规范检测**（基于输入文件所在项目）：
   - 若存在 `raw/会议纪要/`，输出到 `raw/会议纪要/transcribe/`
   - 若存在 `output/`，输出到 `output/transcribe/`
3. **默认回退**：`{输入文件所在项目根目录}/output/transcribe/`

> **跨项目说明**：若你在 A 项目目录下处理 B 项目的文件，输出目录会基于 B 项目（输入文件所在项目）推导。
> **产物定位**：脚本原生输出（`{stem}_字幕_{时间戳}.md`）是**中间产物**；若上游（如 docness collect SOP）有入库命名规范，以调用方规范为准改名搬移。

## 已知限制

- **默认模型无说话人分离**：`qwen3-asr-flash-filetrans` 不返回 `speaker_id`，输出为「片段N」。需要说话人标注时加 `--diarize`（paraformer-v2 + `diarization_enabled`，>2h 自动分块，实测 6 说话人）。原 OpenAI 实现（同名旧版）已于 2026-11-26 移除——无有效 key，本 skill 由 meeting-transcript 改名顶替。

## 静音裁剪与时间轴还原（默认开启）

脚本默认在转写前做静音处理，适合全天录音：

1. **扫描**（秒级）：ffmpeg `silencedetect`，判据为静音占比 > 5% 或单段 > 60s 才裁剪，否则原样上传。
2. **分段裁剪**：把所有 > 20s（`--trim-threshold` 可调）的长静音抠掉，保留段无缝拼接后上传，省计费秒数与上传流量；`--no-trim` 可整体关闭。纯静音上传还会被 DashScope 以 `SUCCESS_WITH_NO_VALID_FRAGMENT` 拒绝，裁剪同时规避该失败。
3. **时间轴还原**：转写完成后，逐字稿时间戳按裁剪台账自动映射回**原片时间**（分段偏移，非单常数），产物为 `*_原片时间.md`，另落 `*_时间轴映射.json` 备查。
4. **验收**：抽检 5 段时间戳，对原片对应位置做 volumedetect 有声探测，全部落在有声区才算还原成功；有静音命中会在 stdout 打警告。

## 结果下载可靠性

DashScope 返回的转写结果 URL 为临时签名链接，有效期较短。脚本已内置兜底机制：

- 若直接下载失败（URL 过期），会自动通过 `task_id` 重新向 DashScope 获取最新 URL
- 若重新获取也失败，会抛出包含 `task_id` 的错误信息，可手动查询任务状态

## 环境依赖

- `ffmpeg`（系统包）
- Python 依赖见 `requirements.txt`（dashscope、requests）。系统 Python 多为 externally managed（PEP 668），裸 `pip install` 会被拒——用 venv：`python3 -m venv <venv路径> && <venv路径>/bin/pip install -r requirements.txt`
- `DASHSCOPE_API_KEY`：先读环境变量，读不到再回退项目根目录 `skills.env`（KEY=VALUE，如 `DASHSCOPE_API_KEY=sk-...`，加入 .gitignore 勿提交；路径可用 `SKILLS_ENV_FILE` 覆盖）

## 示例

```bash
# 基本用法（用 venv 的 python 运行；默认含静音扫描+裁剪+时间轴还原）
python scripts/transcribe.py /path/to/会议录屏.mp4

# 指定输出目录
python scripts/transcribe.py /path/to/会议录音.m4a --output-dir ./output

# 全天录音：放宽轮询预算（默认自适应：至少 600s，按音频时长/4 缩放）
python scripts/transcribe.py /path/to/全天录音.wav --poll-timeout 3600

# 保守模式：只裁更长静音（默认 20s 以上的静音才抠）
python scripts/transcribe.py /path/to/会议.mp4 --trim-threshold 60

# 完全不裁（保持旧行为）
python scripts/transcribe.py /path/to/会议.mp4 --no-trim
```

独立工具 `scripts/silence_map.py`（scan/map/verify 子命令）可在管线外单独使用：预判是否值得裁剪、手工重映射旧逐字稿、对任意逐字稿做原片有声区抽检。
