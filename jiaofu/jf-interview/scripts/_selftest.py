"""check_shaping.py 的内置自检：样例构造 + 运行器（#161 从主脚本拆出）。

主脚本只留判定逻辑与薄的 --self-test 入口；合法/非法 shaping 样例的构造、
十四项断言全在这里。判定依赖经参数注入（validate 与分支可见词表），
不做反向 import——主脚本以 __main__ 运行时按名 import 会加载出第二份模块。

不直接运行本文件，跑：
  python3 check_shaping.py --self-test
"""

import os
import tempfile


def _write(td: str, files: dict):
    for name, text in files.items():
        path = os.path.join(td, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def _valid_sample():
    return {
        "00-intake.md": """# 原始输入与来源

一句话问题：会议室总被占，谁在用说不清。
上游 MRD：docs/meeting-mrd.md（含 2 条 DR 待拍板）
""",
        "01-problem.md": """# 问题定义

行政需要在冲突发生前看清每间会议室的占用与空闲。现状靠门口白板和群里吼，冲突频繁且无法追溯。

## 现在怎么解决

白板登记，先到先得。
""",
        "02-users.md": """# 目标用户与角色

| 角色 | 是谁 | 用本系统做什么 |
|---|---|---|
| 行政 | 管理员 | 看占用、调解冲突 |
| 员工 | 普通用户 | 查空房、订会议室 |
""",
        "03-journey.md": """# 用户旅程

## 主路径
1. 员工查空房 → 订会议室 → 收到确认

## 分支
- **分支：预订时间冲突**：触发：提交时房间已被占；用户看到：booking-form 顶部红色冲突提示与三个相邻空房建议；后续：可改选建议房间或返回重选
- **分支：预订后未签到**：触发：开始时间过 15 分钟未签到；用户看到：meeting-list 该行置灰并标注「已释放」；后续：房间自动释放，记录保留可申诉
""",
        "04-scope.md": """# MVP 边界

## 做
- 查空房与预订（meeting-list / booking-form）

## 暂缓
- 门口大屏占用看板（V2，等硬件到位）

## 不做
- 视频会议设备联动（另有专管系统）

## 待确认
- OQ-01｜释放规则 15 还是 30 分钟（拍板人：行政管理负责人；影响面：meeting-list 状态列与通知文案）
- OQ-02｜是否对接门禁签到数据（拍板人：行政管理负责人；影响面：booking-form 签到方式字段）
""",
        "05-flows.md": """# 关键流程

## 预订
主链：查房 → 锁定 → 确认
异常：锁定后 5 分钟未确认自动解锁；并发预订以后提交者收到冲突分支提示
""",
        "06-shaped-brief.md": """# 定型摘要

会议室占用可视 + 冲突前拦截。主用户行政与员工，MVP 做查房/预订/释放，
看板进 V2。待确认见 07（OQ-01、OQ-02）。
""",
        "07-open-questions.md": """# 待确认清单

- OQ-01｜释放规则 15 还是 30 分钟｜DR: D-01｜影响页面: meeting-list（状态列）｜拍板人: 行政管理负责人｜阻塞: 释放逻辑与通知文案
- OQ-02｜是否对接门禁签到数据｜DR: D-02｜影响页面: booking-form（签到方式字段）｜拍板人: 行政管理负责人｜阻塞: 未签到判定的数据来源
- 冲突-01｜释放规则口径｜影响页面: meeting-list｜拍板人: 行政管理负责人｜阻塞: 同 OQ-01
  - 原话A：「15 分钟没签到就释放」——来源：首次调研会纪要，2026-08-30
  - 原话B：「给 30 分钟缓冲比较合理」——来源：行政负责人邮件，2026-09-05
  - 处置：并列上抛，等行政管理负责人拍板
""",
    }


_SYNONYM_JOURNEY = """# 用户旅程

## 主路径
1. 员工查空房 → 订会议室 → 收到确认

## 分支
- **分支：预订时间冲突**：触发：提交时房间已被占
  - 显示：booking-form 顶部红色冲突提示与三个相邻空房建议
  - 后续：可改选建议房间或返回重选
- **分支：预订后未签到**：触发：开始时间过 15 分钟未签到
  - meeting-list 该行呈现「已释放」置灰态
  - 后续：房间自动释放，记录保留可申诉
- **分支：账号被停用**：触发：提交时账号处于停用状态
  - 弹出阻断弹窗，仅保留「联系行政」入口
  - 后续：账号恢复后可重试，草稿保留
- **分支：预订成功**：触发：提交通过校验
  - 跳转到结果页，展示会议号与二维码
  - 后续：可返回 meeting-list 继续查房
- **分支：网络中断**：触发：提交请求超时
  - 出现「网络异常，请重试」横幅，已填内容不丢
  - 后续：恢复后手动重试即可
"""

_NO_VISIBILITY_JOURNEY = """# 用户旅程

## 主路径
1. 员工查空房 → 订会议室 → 收到确认

## 分支
- **分支：预订时间冲突**：触发：提交时房间已被占
  - 处理：拒绝本次提交并返回三个相邻空房建议
  - 后续：可改选建议房间或返回重选
"""


def _synonym_sample():
    """03-journey.md 全用「看到」的同义词写分支描写——不应误报 G4。"""
    files = _valid_sample()
    files["03-journey.md"] = _SYNONYM_JOURNEY
    return files


def _no_visibility_sample():
    """分支里一个同义词都没有——仍须打回（同义词放宽不能把门禁放到形同虚设）。"""
    files = _valid_sample()
    files["03-journey.md"] = _NO_VISIBILITY_JOURNEY
    return files


# 有序列表写的分支：中文文档常见写法，须与 `- ` 同等对待
_ORDERED_JOURNEY = """# 用户旅程

## 主路径
1. 员工查空房 → 订会议室 → 收到确认

## 分支
1. **分支：预订时间冲突**：触发：提交时房间已被占。用户看到：booking-form 顶部红色冲突提示与三个相邻空房建议。
2. **分支：预订后未签到**：触发：开始时间过 15 分钟未签到。用户看到：meeting-list 该行置灰并标注「已释放」。
"""

# 分支写成 ### 小标题 + 散文：门禁看不见它，必须打回而不是静默跳过
_HEADING_JOURNEY = """# 用户旅程

## 主路径
1. 员工查空房 → 订会议室 → 收到确认

## 分支

### 分支：预订时间冲突

触发：提交时房间已被占。

处理：拒绝本次提交并返回三个相邻空房建议。

### 分支：预订后未签到

触发：开始时间过 15 分钟未签到。

处理：房间自动释放，记录保留可申诉。
"""


def _ordered_journey_sample():
    """分支写成有序列表（`1. `）——不该被漏掉。"""
    files = _valid_sample()
    files["03-journey.md"] = _ORDERED_JOURNEY
    return files


def _heading_journey_sample():
    """分支写成 `### 分支：x` 小标题——门禁认不出条目，须报 ERROR 而非静默。"""
    files = _valid_sample()
    files["03-journey.md"] = _HEADING_JOURNEY
    return files


def _quote_problem_sample():
    """产品定位写成引用块——应按引用块内容校验，而不是滑到下一个段落。"""
    files = _valid_sample()
    files["01-problem.md"] = """# 问题定义

> 行政需要在冲突发生前看清每间会议室的占用与空闲，现状靠门口白板和群里吼。

## 现在怎么解决

白板登记，先到先得。
"""
    return files


def _natural_conflict_sample():
    """两次口径用自然措辞写（说法对不上），且 07 不单列——旧实现全绿放行。"""
    files = _valid_sample()
    files["05-flows.md"] = """# 关键流程

## 预订
主链：查房 → 锁定 → 确认
异常：260811 与 260814 的说法对不上（15 分钟 vs 30 分钟），按后口径先行留痕。
"""
    text07 = files["07-open-questions.md"]
    files["07-open-questions.md"] = text07[:text07.index("- 冲突-01")].rstrip() + "\n"
    return files


def _dr_only_sample():
    """给了 --manifest，却在「影响页面」里写「见 DR 说明」——取不到任何页面 id。"""
    files = _valid_sample()
    files["07-open-questions.md"] = """# 待确认清单

- OQ-01｜释放规则 15 还是 30 分钟｜DR: D-01｜影响页面: 见 DR 说明｜拍板人: 行政管理负责人｜阻塞: 释放逻辑与通知文案
- OQ-02｜是否对接门禁签到数据｜DR: D-02｜影响页面: 会议室预订表单｜拍板人: 行政管理负责人｜阻塞: 签到数据来源
"""
    return files


def _scope_mismatch_sample():
    """07 少登记一条：04-scope 的待确认有 OQ-01、OQ-02，07 只剩 OQ-01。"""
    files = _valid_sample()
    files["07-open-questions.md"] = """# 待确认清单

- OQ-01｜释放规则 15 还是 30 分钟｜DR: D-01｜影响页面: meeting-list（状态列）｜拍板人: 行政管理负责人｜阻塞: 释放逻辑与通知文案
"""
    return files


def _scope_suffix_sample():
    """分类标题写成「## 待确认项」——类别在，不该报「缺少分类标题」。"""
    files = _valid_sample()
    files["04-scope.md"] = files["04-scope.md"].replace("## 待确认", "## 待确认项")
    return files


def _fake_page_id_sample():
    """把 07 的页面 id 换成「形似但非页面」的廉价写法：文档名 / 凭空捏造的 id。"""
    files = _valid_sample()
    files["07-open-questions.md"] = """# 待确认清单

- OQ-01｜释放规则 15 还是 30 分钟｜DR: D-01｜影响页面: open-questions｜拍板人: 行政管理负责人｜阻塞: 释放逻辑与通知文案
- OQ-02｜是否对接门禁签到数据｜影响页面: totally-fake-page｜拍板人: 行政管理负责人｜阻塞: 签到数据来源
"""
    return files


def _sample_manifest():
    """与 _valid_sample 的页面 id 对齐的最小 manifest（G5 交叉校验用）。"""
    return {"schemaVersion": 1, "product": {"name": "会议室系统", "type": "Web"},
            "modules": [{"id": "meeting", "title": "会议室"}],
            "pages": [{"id": "meeting-list", "title": "会议室列表", "moduleId": "meeting"},
                      {"id": "booking-form", "title": "预订表单", "moduleId": "meeting"}]}


def _invalid_sample():
    return {
        "00-intake.md": """# 原始输入与来源

一句话问题：会议室总被占。上游文档：口头描述。
""",
        "01-problem.md": """# 问题定义

行政需要看清占用。员工需要快速订房。主管需要统计。IT 需要对接门禁。前台需要代订。定位写不下就继续写。

## 现在怎么解决

白板登记。
""",
        "02-users.md": """# 目标用户与角色

| 角色 | 用途 |
|---|---|
| 行政 | 管理 |

注意：行政与主管对释放规则的口径不一致，待理清。
""",
        "03-journey.md": """# 用户旅程

## 主路径
1. 查房 → 订房

## 分支
- **分支：时间冲突**：触发：房间被占；后续：待定
- **分支：未签到**：触发：超时；后续：自动释放
""",
        "04-scope.md": """# MVP 边界

## 做
- 查房与预订

## 不做
- 设备联动

## 待确认
- 释放规则多少分钟
""",
        "05-flows.md": "",
        "07-open-questions.md": """# 待确认清单

- OQ-01｜释放规则多少分钟｜影响页面: 见上文｜拍板人: 行政
""",
    }


def run(validate, branch_visible_words) -> int:
    """跑内置样例断言；validate 与词表由 check_shaping.py 注入。"""
    print("=== check_shaping.py 自检 ===")
    ok = True

    with tempfile.TemporaryDirectory() as td:
        # 1) 合法样例：期望 0 error
        vdir = os.path.join(td, "valid", "shaping")
        _write(vdir, _valid_sample())
        rep = validate(vdir)
        if rep.errors:
            ok = False
            print("❌ 合法样例应无 ERROR，实际 %d 条：" % len(rep.errors))
            for i in rep.errors:
                print(i)
        else:
            print("✅ 合法样例：0 error（警告 %d 条）" % len(rep.warnings))

        # 2) 非法样例：期望逐条报出 G1–G7
        idir = os.path.join(td, "invalid", "shaping")
        _write(idir, _invalid_sample())
        rep2 = validate(idir)
        codes = {i.code for i in rep2.errors}
        expected = {"G1", "G2", "G3", "G4", "G5", "G6", "G7"}
        missing = expected - codes
        if missing:
            ok = False
            print("❌ 非法样例未报出的规则码：%s" % ", ".join(sorted(missing)))
        else:
            print("✅ 非法样例：G1–G7 全部命中（共 %d 条错误）" % len(rep2.errors))

        # 3) G4 同义词：显示/展示/呈现/出现/弹出/跳转到 写分支描写不得误报
        sdir = os.path.join(td, "synonym", "shaping")
        _write(sdir, _synonym_sample())
        rep3 = validate(sdir)
        if rep3.errors:
            ok = False
            print("❌ G4 同义词写法被误报为 ERROR：%d 条" % len(rep3.errors))
            for i in rep3.errors:
                print(i)
        else:
            print("✅ G4 同义词写法（%s）不被误报：0 error"
                  % "/".join(branch_visible_words))

        # 4) G4 反向：分支里一个同义词都没有，仍须打回
        ndir = os.path.join(td, "novisibility", "shaping")
        _write(ndir, _no_visibility_sample())
        rep4 = validate(ndir)
        if not any(i.code == "G4" for i in rep4.errors):
            ok = False
            print("❌ 分支未写「用户看到什么」时应报 G4，实际未报")
        else:
            print("✅ G4 反向：分支无任何「看到/显示/…」字样仍被打回")

        # 5) G5 交叉校验：给了 --manifest，假页面 id 必须被拒
        fdir = os.path.join(td, "fakepage", "shaping")
        _write(fdir, _fake_page_id_sample())
        page_ids = {p["id"] for p in _sample_manifest()["pages"]}
        rep5 = validate(fdir, page_ids)
        rep5_msg = " ".join(i.message for i in rep5.errors if i.code == "G5")
        if "totally-fake-page" not in rep5_msg:
            ok = False
            print("❌ --manifest 下凭空捏造的页面 id 未被拒（G5）：%r" % rep5_msg[:120])
        else:
            print("✅ G5 交叉校验：--manifest 下假页面 id（totally-fake-page）被拒")

        # 6) G5 交叉校验：页面 id 与 manifest 一致时不得误报
        rep6 = validate(vdir, page_ids)
        if rep6.errors:
            ok = False
            print("❌ 页面 id 与 manifest 一致时应 0 error，实际 %d 条：" % len(rep6.errors))
            for i in rep6.errors:
                print(i)
        else:
            print("✅ G5 交叉校验：页面 id 与 manifest 一致时不误报")

        # 7) G5 无 --manifest：文档名/skill 名不计为页面 id，且给 WARN 而非静默通过
        rep7 = validate(fdir)
        g5_warns = " ".join(i.message for i in rep7.warnings if i.code == "G5")
        if "open-questions" not in g5_warns:
            ok = False
            print("❌ 无 --manifest 时，open-questions 这类文档名应给 WARN：%r"
                  % g5_warns[:120])
        else:
            print("✅ G5：无 --manifest 时文档名/skill 名被排除并给 WARN（不静默通过）")

        # 8) G4：有序列表（1. ）写的分支要被认出来
        odir = os.path.join(td, "ordered", "shaping")
        _write(odir, _ordered_journey_sample())
        rep8 = validate(odir)
        if rep8.errors:
            ok = False
            print("❌ 有序列表写的分支被误判：%d 条" % len(rep8.errors))
            for i in rep8.errors:
                print(i)
        else:
            print("✅ G4：有序列表（`1. `）写的分支被识别并同样校验")

        # 9) G4 反向：分支写成 `### 分支：x` 小标题——门禁认不出，须打回而非静默
        hdir = os.path.join(td, "heading", "shaping")
        _write(hdir, _heading_journey_sample())
        rep9 = validate(hdir)
        if not any(i.code == "G4" for i in rep9.errors):
            ok = False
            print("❌ 分支写成 ### 小标题时应报 G4（门禁无法校验），实际未报")
        else:
            print("✅ G4 反向：分支写成小标题时打回（不再静默跳过）")

        # 10) G2：定位写成引用块，按引用块内容校验，不滑到下一段
        qdir = os.path.join(td, "quote", "shaping")
        _write(qdir, _quote_problem_sample())
        rep10 = validate(qdir)
        if rep10.errors:
            ok = False
            print("❌ 引用块写的产品定位被误报：%d 条" % len(rep10.errors))
            for i in rep10.errors:
                print(i)
        else:
            print("✅ G2：产品定位写成引用块时校验引用块本身（不再滑到下一段）")

        # 11) G6：自然措辞的两次口径必须打回，并回显命中的原句
        cdir = os.path.join(td, "conflict", "shaping")
        _write(cdir, _natural_conflict_sample())
        rep11 = validate(cdir)
        g6 = [i for i in rep11.errors if i.code == "G6"]
        if not g6 or "说法对不上" not in g6[0].message:
            ok = False
            print("❌ 自然措辞的两次口径（说法对不上）未报 G6")
        else:
            print("✅ G6：自然措辞的两次口径被打回并回显原句")

        # 12) G5：给了 --manifest 却取不到页面 id（「见 DR 说明」/中文页面名）→ ERROR
        ddir = os.path.join(td, "dronly", "shaping")
        _write(ddir, _dr_only_sample())
        rep12 = validate(ddir, page_ids)
        g5_err = " ".join(i.message for i in rep12.errors if i.code == "G5")
        if "见 DR 说明" not in g5_err or "会议室预订表单" not in g5_err:
            ok = False
            print("❌ --manifest 下「影响页面」里没有页面 id 时应报 G5 并回显现写的值，"
                  "实际：%r" % g5_err[:120])
        else:
            print("✅ G5：--manifest 下取不到页面 id（DR 说明 / 中文页面名）时打回")

        # 13) G7：04-scope 的待确认与 07 编号必须一一对应
        mdir = os.path.join(td, "mismatch", "shaping")
        _write(mdir, _scope_mismatch_sample())
        rep13 = validate(mdir)
        if not any(i.code == "G7" and "OQ-02" in i.message for i in rep13.errors):
            ok = False
            print("❌ 07 少登记一条（OQ-02）时应报 G7，实际未报")
        else:
            print("✅ G7：07 少登记待确认条目时打回（OQ-02 悬空）")

        # 14) G3：「待确认项」这类分类标题后缀不该被误报为缺分类
        sfx = os.path.join(td, "suffix", "shaping")
        _write(sfx, _scope_suffix_sample())
        rep14 = validate(sfx)
        if any(i.code in ("G3", "G7") for i in rep14.errors):
            ok = False
            print("❌ 分类标题写「待确认项」被误报：")
            for i in rep14.errors:
                print(i)
        else:
            print("✅ G3：「待确认项」分类标题后缀不再误报")

    print("=== 自检%s ===" % ("通过" if ok else "失败"))
    return 0 if ok else 1
