---
name: jf-validate
description: 交付·验证——manifest.json 与原型产物的校验门禁。触发：校验 manifest、契约不通过、validate、原型自检、门禁。
---

# 验证门禁

对 manifest.json 与渲染后的原型做机器校验，**不通过即打回**。
校验项 = `jf-contract` 定义的不变条件 I1–I12 + 文件/HTML 级 F1–F4。
这是 jf-* 链路里唯一「能自动说不对」的地方——产物错了不该靠人眼看出来。

## 入口纪律

**正常路径**：三拍按需调用（哪一拍用契约/门禁，就由哪一拍调）。
**独立路径**：用户显式指名时可直接调用。

**典型误入**：
- 想「懂契约字段含义」→ `jf-contract`
- 想「产出 manifest」→ `jf-ia`
- 想「从 manifest 生成 HTML」→ `jf-uxprompt`（生成后回调本 skill 自检）

## 用法

```bash
# 校验（默认：未渲染的文件缺失只警告）
python3 scripts/validate_manifest.py manifest.json

# 严格模式：警告也判失败（CI / 交付前）
python3 scripts/validate_manifest.py manifest.json --strict

# 指定 file 字段的根目录（默认 manifest 所在目录）
python3 scripts/validate_manifest.py manifest.json --root /path/to/project

# 机读报告
python3 scripts/validate_manifest.py manifest.json --json

# 校验脚本本身的正确性（内置合法/非法样例）
python3 scripts/validate_manifest.py --self-test
```

退出码：`0` 通过（无 ERROR）｜`1` 未通过（有 ERROR，或 `--strict` 下有 WARN）｜`2` 用法错误或 manifest 无法解析。

## 校验项

| 码 | 条件 | 级别 |
|---|---|---|
| I1 | `page.id` 必须等于 `page.file` 的 basename | ERROR |
| I2 | `relations[].from/to` 必须引用已存在的 page | ERROR |
| I3 | `sub-flow` 页必须有 `hostPageId`，且宿主页是 `standalone` | ERROR |
| I4 | ID 只用小写字母+数字+连字符，且集合内唯一 | ERROR |
| I5 | `device` ∈ {desktop, mobile}，`viewport` 宽高正整数 | ERROR |
| I6 | 每个 module 至少被一个 page 引用 | ERROR |
| I7 | `crud` 含 `D` 必须写 `crudNote`（业务替代动作） | ERROR |
| I8 | `states` 非空且含 `default` | ERROR |
| I9 | `components[].usedBy` 引用的 page 必须存在 | ERROR |
| I10 | `route` → 目标 `frame: route`；`modal` → 目标 `frame: modal` 且 `hostPageId == from` | ERROR |
| I11 | `design` 块：字段非空且指向真实存在的文件；只有 `tokens`/`components` 而无 `spec`/`states` 时提醒徽标挂不上 | 类型错/空值 ERROR；文件缺失与提醒 WARN（`--strict` → ERROR） |
| I12 | `scenes[]` 声明后：`source` 非空、`title` 不含 FR/AC/BR/SM/UC 编号、`moduleId`/`pageId` 引用存在、每步 `state` ∈ 该页 `states` | ERROR |
| S0 | 结构/必填/枚举类基础错误（缺 title、nav 非法、`annotations[].status` 不在三态词表、同页 `annotations[].id` 重复等） | ERROR |
| F1 | `pages[].file` 指向的文件不存在 | WARN（`--strict` → ERROR） |
| F2 | HTML 内 `data-nav` 指向不存在的页面 | ERROR |
| F3 | 跳转链接与 relations **双向一致**：relation 无对应链接，或链接未声明 relation | WARN（`--strict` → ERROR） |
| F4 | 标注 `target` 在对应 HTML 中找不到元素，或违反协议（nth-child / 文案 / 非法形式） | ERROR（未渲染时 WARN） |

F3 的判定细节（两个方向都有豁免，属渲染器约定而非漏判）：
- sub-flow 源页的链接渲染在**宿主页**的「从属与跳转」区，因此 F3 会在宿主页而非源页里找链接
- 侧边导航与「由谁激活」的宿主回链是**结构性链接**，不要求声明 relation

F4 管到哪为止（与渲染器分工，别指望它兜住）：
- F4 判的是「渲染器输出与 manifest 自洽」——manifest 里的 target 在产物里
  能否找到对应元素，判定就是**字符串查找**
- 「这条标注是否落在**真实业务元素**上」F4 判不了（`#btn-create` 与一个
  恰好同名的占位元素在字符串层面没有区别）。**「造个同名 id 混过 F4」今天
  依然做得到**，F4 拦不住——它的设计目标不是拦这个
- 拦这个的是两条：渲染器的**未落点 WARN**（标注落不到页面上会进「评审标注 ·
  未落点」区并向 stderr 报 WARN），以及**评审时的纪律**（jf-review 必须把
  未落点标注显式带出）。门禁只管自洽，落差靠这两条暴露
- **F4 只对 canonical 树适用**（`pages[].file` 指向的那棵）。客户演示档
  （`render_manifest.py --demo`，P2 落地后可用）按设计不含标注层，「annotations 的 target 找不到
  元素」在它里面是**不适用**而非**不自洽**——演示树的门禁是
  `check_demo_separation.py`（P4）与 `jf_contract_check.py` 的链接可达性

## 门禁时机

| 时机 | 命令 | 未通过的处置 |
|---|---|---|
| `jf-ia` 产出 manifest 后 | 默认模式 | 打回 jf-ia 修契约，不进线框 |
| `jf-uxprompt` 渲染完成后 | `--strict` | 打回重渲染，不进评审 |
| 交付客户前 | `--strict` | 不交付 |
| 外部 skill 产出后 | 默认 + `--strict` | **不信任外部输出，只看契约** |

## 纪律

- **以契约验收，不信任产出**：外部 skill 的产物与本仓库产物走同一道门禁，没有例外
- **先修契约再修页面**：I 类错误说明契约本身错，改页面无意义
- **WARN 也要交代**：F1 在渲染前出现是正常的，渲染后仍有就是缺陷
- **自检先行**：改完脚本先跑 `--self-test`，再拿真实 manifest 验

## 项目适配

- **目录路径**：manifest 与 prototypes 的位置由项目结构决定，用 `--root` 对齐
- **执行外包**：本 skill 的**校验**是 jf-* 保留能力，不外仓；外部增强（如 `impeccable audit`
  做视觉/a11y 检查）是**额外**门禁，不替代本脚本
- **接入 CI**：`--strict --json` 可直接接流水线
