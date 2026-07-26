"""Tests for state.py"""

import tempfile
from pathlib import Path

from scripts.state import (
    read_front_matter,
    record_collect,
    record_process,
    record_publish,
    write_front_matter,
)


def test_read_empty_file():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# 测试")
        tmp = Path(f.name)

    try:
        result = read_front_matter(tmp)
        assert result == {}
    finally:
        tmp.unlink()


def test_read_and_write_front_matter():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# 测试\n\n内容")
        tmp = Path(f.name)

    try:
        write_front_matter(tmp, {"source": "https://test.com", "status": "collected"})
        result = read_front_matter(tmp)
        assert result["source"] == "https://test.com"
        assert result["status"] == "collected"
    finally:
        tmp.unlink()


def test_read_existing_front_matter():
    content = "---\ndocness:\n  source: https://test.com\n  status: collected\n---\n\n# 测试"
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write(content)
        tmp = Path(f.name)

    try:
        result = read_front_matter(tmp)
        assert result["source"] == "https://test.com"
        assert result["status"] == "collected"
    finally:
        tmp.unlink()


def test_record_collect():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# 测试")
        tmp = Path(f.name)

    try:
        record_collect(tmp, "https://test.com", "tencent-docs", "会议纪要", "foo.docx")
        result = read_front_matter(tmp)
        assert result["source"] == "https://test.com"
        assert result["source_type"] == "tencent-docs"
        assert result["knowledge_category"] == "会议纪要"
        assert result["original_filename"] == "foo.docx"
        assert result["status"] == "collected"
    finally:
        tmp.unlink()


def test_record_process():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# 测试")
        tmp = Path(f.name)

    try:
        record_collect(tmp, "https://test.com", "webpage", "参考资料")
        record_process(tmp, "illustrate", "baoyu-image-gen", ["发件箱/out.md"])
        result = read_front_matter(tmp)
        assert result["status"] == "processed"
        assert len(result["processing"]) == 1
        assert result["processing"][0]["action"] == "illustrate"
    finally:
        tmp.unlink()


def test_record_publish():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# 测试")
        tmp = Path(f.name)

    try:
        record_collect(tmp, "https://test.com", "webpage", "参考资料")
        record_publish(tmp, "feishu", "token123", "https://feishu.cn/doc")
        result = read_front_matter(tmp)
        assert result["status"] == "published"
        assert len(result["published"]) == 1
        assert result["published"][0]["target"] == "feishu"
    finally:
        tmp.unlink()
