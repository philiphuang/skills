---
name: jf-contract
description: 交付·契约——manifest.json 的唯一权威定义。触发：manifest、页面契约、契约字段、不变条件、跳转协议、标注协议。
---

# 契约层

manifest.json 是 jf-* 套件的**唯一真相源**：页面、跳转、组件、标注全部以它为准。
本 skill 只做一件事——**定义契约**。不产出业务内容，不做页面设计，不渲染 HTML。
谁要读/写 manifest，都引用本 skill；校验走 `jf-validate`，渲染走 `jf-uxprompt`。

## 入口纪律

**正常路径**：三拍按需调用（哪一拍用契约/门禁，就由哪一拍调）。
**独立路径**：用户显式指名时可直接调用。

**典型误入**：
- 想「校验 manifest 对不对」→ `jf-validate`
- 想「从 manifest 生成 HTML」→ `jf-uxprompt`
- 想「推导页面清单和导航」→ `jf-ia`（产出 manifest）

## 契约全文

**`references/manifest-schema.md` 是唯一权威版本**，包含：

- 顶层结构（`schemaVersion` / `product` / `design` / `modules[]` / `pages[]` / `relations[]` / `components[]` / `annotations` / `scenes[]`）
- 每个字段的类型、必填性、条件必填
- 不变条件 **I1–I12**（I1–I10 与 I12 硬错误，I11 是唯一分级的一条）+ F1–F4（文件/HTML 级）
- 跳转协议 `<a href="./<id>.html" data-nav="<id>">`
- 标注协议（禁猜坐标、稳定 selector、status 三态、气泡与未落点语义）
- ID 命名规则
- **jf-ia 文档表 → manifest 的字段映射表**
- 完整示例

改契约只改这一个文件；`jf-validate` 的校验项和 `jf-uxprompt` 的渲染器都以它为准同步。

`references/` 下还有一份套件级资产：**`references/external-skills.md`——jf-* 执行外包登记表（中央表）**。
各拍内步骤的外部执行者（候选全名 / 安装来源 / 适配层输入 / 产出门禁 / 失败语义）以**步骤为主键**（S1–S7）登记在那里，
各 skill 的「项目适配 · 执行外包」一律指到它，不再各自维护。

## 为什么需要这一层

jf-* 的产物原本是给人读的文档块（BO/PS/LT/NM/FA、PW/GC/CSM）——描述性内容。
而 HTML 生成需要**可遍历的结构**：页面 ID → 文件 → 组件 → 跳转 → 标注。
没有这层，每次「生成页面」都是把文档重新猜一遍，细节必然丢。

manifest 同时解决三件事：

| 用途 | 消费方 |
|---|---|
| 生成器的输入 | `jf-uxprompt`（遍历 pages 出 HTML） |
| 研发的路由表 | `relations[]` + `pages[].file` |
| 客户评审的标注索引 | `annotations` 按 pageId 挂载 |

## 不变条件 I1–I12（速查）

| # | 条件 |
|---|---|
| I1 | `page.id` 必须等于 `page.file` 的 basename |
| I2 | `relations[].from/to` 必须引用已存在的 page |
| I3 | `sub-flow` 页必须有 `hostPageId`，且宿主页是 `standalone` |
| I4 | ID 只用小写字母+数字+连字符，集合内唯一 |
| I5 | `device` ∈ {desktop, mobile}，`viewport` 正整数 |
| I6 | 每个 module 至少被一个 page 引用 |
| I7 | `crud` 含 `D` 必须写业务替代动作，不写物理删除 |
| I8 | `states` 非空且含 `default` |
| I9 | `components[].usedBy` 引用的 page 必须存在 |
| I10 | `route` → 全幅页；`modal` → 弹窗且 `hostPageId == from` |
| I11 | `design` 块字段非空且指向真实文件（文件缺失默认 WARN，`--strict` ERROR） |
| I12 | `scenes[]`：`source` 非空、`title` 不含 FR/AC/BR/SM/UC 编号、`moduleId`/`pageId` 引用存在、每步 `state` ∈ 该页 `states` |

完整定义（含分级理由与逐字段说明）见 `references/manifest-schema.md`，此处只作速查。

## 纪律

- **单一真相源**：manifest 与文档表冲突时以 manifest 为准，文档表由 manifest 派生
- **先定 nav 再定 frame**：能不能直达决定 `nav`，NM 类型列决定 `frame`，两者不一致即缺陷
- **禁猜坐标**：标注锚点必须有稳定 selector，坐标只在渲染后落点
- **不假装落点**：标注落不到真实元素上时，显式进「未落点」区 + 报 WARN；
  给自己造一个同名元素混过 F4 是骗评审，比承认没落点更糟
- **不改契约迁就产出**：外部 skill 输出不合规时打回重做，而不是放宽契约

## 项目适配

- **目录路径**：manifest 的存放位置由项目结构决定，默认与 PRD 同级（`manifest.json`）
- **执行外包**：本 skill 是契约定义，不外包；但套件级的外包登记表落在本 skill 的 `references/external-skills.md`
- **版本演进**：`schemaVersion` 递增时，旧版本 manifest 由 `jf-validate` 提示迁移，不静默失败
