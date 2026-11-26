# transcribe

会议录音/录像自动转写为 Markdown 字幕。

## 安装依赖

### 1. ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg
```

### 2. Python 依赖

系统 Python 多为 externally managed（PEP 668），裸 `pip install` 会被拒，用 venv：

```bash
python3 -m venv <venv路径>
<venv路径>/bin/pip install -r requirements.txt
```

### 3. 配置 API Key

```bash
export DASHSCOPE_API_KEY="your-api-key"
```

## 使用方法

```bash
python scripts/transcribe.py /path/to/会议录屏.mp4 --output-dir ./output
```

## 输出格式

```markdown
# 会议录屏 会议字幕

- 音频格式: wav
- 采样率: 16000

**[00:00:00 - 00:00:21] 片段1**

> 这个项目可能就要下周能够立项...
```

> 说明：当前模型（qwen3-asr-flash-filetrans）不返回说话人标识，分段显示为「片段N」；
> 仅当 ASR 返回 speaker_id 时才会出现「说话人N」。纯静音输入会被 DashScope 以
> `SUCCESS_WITH_NO_VALID_FRAGMENT` 拒绝——脚本默认已内置静音扫描＋分段裁剪（`--no-trim` 关闭），
> 裁剪后时间戳自动映射回原片时间，产物 `*_原片时间.md` 附带 `*_时间轴映射.json` 台账。
