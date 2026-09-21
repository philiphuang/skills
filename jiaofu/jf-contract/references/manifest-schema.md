# manifest.json 契约

> jf-* 套件的**唯一真相源**。页面、跳转、组件、标注全部以本文件为准。
> 校验实现：`products/jiaofu/jf-validate/scripts/validate_manifest.py`
> 渲染实现：`products/jiaofu/jf-uxprompt/scripts/render_manifest.py`

manifest 同时是三样东西：

1. **生成器的输入** —— 渲染器遍历 `pages[]` 出 HTML，无需再读文档猜结构
2. **研发的路由表** —— `relations[]` 即页面跳转关系，`pages[].file` 即产物路径
3. **客户评审的标注索引** —— `annotations` 按 `pageId` 挂载，评审时按编号对齐

---

## 顶层结构

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schemaVersion` | int | ✅ | 当前为 `1` |
| `product` | object | ✅ | 产品名、形态、上游来源路径 |
| `design` | object | ⭕ | token/组件库路径（Phase 2 起必填） |
| `modules[]` | array | ✅ | 模块（= 领域切片），至少一个 |
| `pages[]` | array | ✅ | 页面清单，至少一个 |
| `relations[]` | array | ✅ | 页面间跳转，可为空数组 |
| `components[]` | array | ⭕ | 公共组件及其被引用页面 |
| `annotations` | object | ⭕ | `{ "<pageId>": [annotation, ...] }` |
| `scenes[]` | array | ⭕ | 客户演示档的场景清单（第三产出档）；不写就不校验 |

### product

```json
{
  "name": "XX系统",
  "type": "Web",
  "source": { "mrd": "docs/x-mrd.md", "prd": "docs/x-prd.md" }
}
```

- `type`：`Web` | `Mobile` | `Desktop`
- `source` 指向上游文档，便于追溯；路径相对 manifest 所在目录

### design（Phase 2 起必填）

```json
{
  "tokens": "prototypes/shared/tokens.css",
  "components": "prototypes/shared/components.js",
  "spec": "DESIGN.md",
  "states": "components-and-states.md"
}
```

---

## modules[]

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 小写字母+数字+连字符，如 `demand` |
| `title` | string | ✅ | 中文名，如「需求管理」 |
| `kind` | string | ⭕ | `prd` \| `platform` \| `external`，默认 `prd` |
| `navNumber` | string | ⭕ | 侧边导航序号，如 `"01"` |

模块 = 领域切片，组内页面共享同一聚合根（对齐 jf-ia 的 BO 块）。

## pages[]

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | **必须等于 `file` 的 basename**（I1） |
| `title` | string | ✅ | 中文页面名 |
| `moduleId` | string | ✅ | 引用 `modules[].id` |
| `file` | string | ✅ | 相对路径，如 `prototypes/pages/demand-list.html` |
| `kind` | string | ✅ | `list` \| `detail` \| `form` \| `dashboard` \| `confirm` \| `external` |
| `nav` | string | ✅ | `standalone`（进导航树）\| `sub-flow`（不进导航树） |
| `frame` | string | ✅ | `route`（全幅页）\| `modal`（挂宿主页内的弹窗） |
| `obj` | string | ✅ | 主管理对象（取自 BO 第 5 步），如「需求项目」 |
| `crud` | string | ✅ | `C`/`R`/`U`/`D` 组合，如 `"CRU"`；`D` 必须配 `crudNote` |
| `crudNote` | string | 条件 | `crud` 含 `D` 时必填，写业务替代动作（I7） |
| `device` | string | ✅ | `desktop` \| `mobile` |
| `viewport` | object | ✅ | `{ "width": 1440, "height": 900 }`，正整数 |
| `states` | array | ✅ | 至少含 `"default"`（I8）；建议 `default/empty/loading/error`，业务态用 `editing`/`warning`/`blocked`/`success` |
| `hostPageId` | string\|null | 条件 | `nav: sub-flow` 或 `frame: modal` 时必填（I3/I10） |
| `fr` | array | ⭕ | 承载的 FR 编号，如 `["FR-05"]` |
| `ac` | array | ⭕ | 对应 AC 编号，如 `["AC-05-1"]` |
| `externalUrl` | string | 条件 | `kind: external` 时必填 |
| `note` | string | ⭕ | 备注（评审要点、待确认） |

### kind 与渲染骨架的对应关系（渲染器约定）

| kind | 骨架 | 典型页面 |
|---|---|---|
| `list` | 筛选区 + 表格 + 分页 | 列表页 |
| `detail` | 描述列表 + 分区块 | 详情页 |
| `form` | 表单字段 + 提交栏 | 新增/编辑页 |
| `dashboard` | 指标卡 + 图表占位 | 看板/驾驶舱 |
| `confirm` | 提示文案 + 确认/取消 | 二次确认弹窗 |
| `external` | 外链说明卡 | 免登录外部页 |

渲染器对每页下部输出「从属与跳转」区，分四类：**激活子流程 / 由谁激活 /
下钻·返回·相关 / 外部链接**（`type: external` 或目标 `kind: external` 的关系归入外部链接）。

## relations[]

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 如 `r-list-detail` |
| `from` | string | ✅ | 源页面 id，必须存在（I2） |
| `to` | string | ✅ | 目标页面 id，必须存在（I2） |
| `label` | string | ✅ | 跳转文案，渲染为链接文字 |
| `type` | string | ✅ | `route` \| `modal` \| `tab` \| `external` |
| `semantic` | string | ⭕ | `drill`（下钻）\| `back`（返回）\| `rel`（相关）\| `activate`（激活子流程） |
| `trigger` | string | ⭕ | CSS selector，如 `[data-nav=demand-detail]` |
| `condition` | string | ⭕ | 触发条件，如「行点击」「有权限时」 |

`type` 与页面框架的对应由 I10 强制：`route` → 目标必须是 `frame: route`；`modal` → 目标必须是 `frame: modal` 且 `hostPageId == from`。

## components[]

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 如 `page-shell` |
| `title` | string | ✅ | 中文名 |
| `usedBy` | array | ✅ | 引用页面 id，必须都存在（I9） |
| `states` | array | ⭕ | `default/hover/active/disabled`（Phase 2 起必填） |

## annotations

```json
{
  "annotations": {
    "demand-list": [
      {
        "id": "a-demand-list-001",
        "number": 1,
        "target": "#btn-create",
        "anchor": { "x": 1, "y": 0.5 },
        "title": "新增需求",
        "content": "对应 PRD §FR-05；无权限时禁用",
        "status": "active"
      }
    ]
  }
}
```

- `target` 只允许两种稳定形式：`#id` 与 `[data-annotation-anchor=值]`；
  **禁止**依赖 `nth-child` / 显示文案 / 复合 selector（F4 校验强制）
- **同一页内 `id` 必须唯一**：气泡的元素 id 由它派生（`ann-<pageId>-<id>`），
  重名会让两条标注指向同一个气泡——点第二条弹出的是第一条的正文，
  而门禁退出码照样是 0。渲染器不信任作者写的 id，撞了会自动加后缀，
  但那是兜底不是许可；S0 会直接报 ERROR
- **`anchor` 当前无消费者**：字段留着是为了将来外部执行者按坐标落点，
  内置渲染器只读 `target`，不读 `anchor`；写不写都不影响渲染与校验
- **禁止凭空猜坐标**；无稳定 target 时必须在固定视口实际渲染后落点
- 删除旧标注不复用 `number`

### status 三态

| 值 | 含义 | 评审现场 |
|---|---|---|
| `active` | 待确认（**缺省值**，不写即此态） | 徽标 accent 蓝（描边+蓝字，hover 反白）；这条要当着客户面过 |
| `resolved` | 已答复 | 徽标转灰；气泡左侧竖条由蓝转灰——「这条不用再问了」 |
| `rejected` | 客户否决 | 徽标转红；气泡左侧竖条转红。答复必须带出到反馈记录（见 jf-review） |

三态都只在**颜色**上有差别（`jf-ann--<status>` / `jf-bubble--<status>`），
没有形状、图标或折叠行为上的不同——别在文档里写「对勾态」「实心」这类
代码里不存在的视觉承诺（曾经写过，评审时按文档找不到，只能一个个去查 CSS）。

非法值由 `jf-validate` 的 S0 报 ERROR。词表在渲染器
（`render_manifest.ANNOTATION_STATUS`）与门禁（`validate_manifest.VALID_ANNOTATION_STATUS`）
各存一份常量——两脚本分属不同 skill、以子进程各自运行，没法共享；
一致性由 `tests/unit/scripts/test_render_manifest.py` 的用例盯着。

### 气泡协议

标注在页面上以**编号徽标**呈现：

| 环节 | 约定 |
|---|---|
| 徽标位置 | 插在 target 命中元素的**开标签之后**（即徽标是那个元素的子节点）。挂在元素外面等于挂错控件，评审时点到的不是同一个东西 |
| 点击行为 | 点徽标弹出气泡浮层（`title` + `content` + 状态 + target）；Esc / 点遮罩关闭。复用 modal 的委托 click + backdrop 模式 |
| 静态可读 | 页面下部有一个 `<details class="jf-ann-all">` 静态全览，**收录全部标注**的编号/标题/状态/正文。气泡是 `display:none` 的浮层、唯一打开路径是 JS，静态全览是它唯一的无脚本副本——落点标注的正文不得只活在气泡里 |
| 三态样式 | 徽标与气泡各带 `jf-ann--<status>` / `jf-bubble--<status>` 类 |
| 同锚点顺序 | 同一锚点上的多条标注一律按 manifest 顺序从左到右排（渲染器倒序注入、徽标紧贴开标签，两者相抵） |

**三支判定**（渲染器落点时的唯一分支依据）：

1. `target` 已在页面正文里 → 徽标挂到该元素上（真实气泡）
2. `target` 命中骨架锚点 → 同上
3. 都不中 → 进页面下部的「**评审标注 · 未落点**」区（虚框），
   渲染器同时向 stderr 报 WARN，列出未落点的标注 id

第 3 支是**显式承认没落点**，不是错误：外部执行者未接入时，骨架里本来
就没有「批量审批按钮」这类业务元素——给它造一个假的当落点才是骗评审。
未落点条目自己带锚点（`id`），徽标也照挂（挂在条目上，气泡照样点得开），
所以 F4 仍然过——**F4 的语义只是「渲染器输出与 manifest 自洽」**，
「其实没落到页面上」这件事由渲染器 WARN 与区标题暴露，**不靠 F4**。
各管一段：F4 管自洽，WARN 管落差。

**演示档不渲染标注层**：客户演示档（`render_manifest.py --demo`，见 jf-uxprompt）
出的页面**不挂编号徽标、不出未落点区、不渲染页面 meta 行**——标注是设计评审的索引，
评审现场逐条过（见 jf-review），不是给客户看的东西。同一份 manifest 出两棵树，
**两场会、两棵树**：带标注层的给设计评审，不带的给客户演示。

**F4 只对 canonical 树适用**，即 `pages[].file` 指向的那棵（不带 `--demo` 渲染出来的
那棵）。演示树按设计不含标注层，`annotations` 的 target 在它里面本来就找不到——
那是**不适用**，不是**不自洽**。演示树有自己的门禁（P2/P4 落地后可用）：
`jf-uxprompt/scripts/check_demo_separation.py`（正文层零 PM 注释，P4），
外加 `jf_contract_check.py` 的链接可达性（`?state=` 已在比对前剥掉）。

### 骨架锚点命名

内置渲染器（降级方案）给自己生成的元素种的锚点，
供标注在无真实业务元素时落点。纯新增属性，不是 schema 字段：

| 元素 | 锚点值 |
|---|---|
| 状态切换按钮 | `state-<状态>`（如 `state-empty`） |
| 「从属与跳转」区每个链接 | `rel-<渲染所在页>-<链接目标页>`，两段都是 pageId |
| modal 浮层 | `modal-<pageId>` |

`rel-` 的方向是**先源后目标**（`rel-demand-list-demand-detail` = 需求列表页上
那个指向需求详情页的链接），不是「先目标后源」。子流程页的链接渲染在宿主页，
所以 `<渲染所在页>` 是宿主页的 pageId，不是子流程页自己的。

外部执行者产出的真实页面里，业务元素用自己的 `id` 或自定的
`data-annotation-anchor` 值，不受此表约束。

---

## scenes[]

**客户演示档**（jf-uxprompt 的第三产出档，渲染成 `console.html`）的场景清单。
**整块可选**——没打算做客户演示就不必写；写了才受 I12 约束。

```json
"scenes": [
  {
    "id": "score-penalty-limit",
    "moduleId": "score",
    "title": "基础积分达上限",
    "source": "AC-05-3",
    "flow": "月度打分",
    "steps": [
      { "pageId": "score-form", "state": "warning", "label": "给分时触顶" },
      { "pageId": "score-detail", "state": "default", "label": "查看留痕" }
    ]
  }
]
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 小写字母+数字+连字符，集合内唯一（I4） |
| `moduleId` | string | ✅ | 引用 `modules[].id` |
| `title` | string | ✅ | **客户可读**的场景名，不含 FR/AC/BR/SM/UC 编号（I12 强制） |
| `source` | string | ✅ | **追溯来源**：FR/AC/BR/SM/UC 编号或文档锚点（I12 强制） |
| `flow` | string | ⭕ | 所属业务主流程名 |
| `steps[]` | array | ✅ | 至少一步 |

`steps[]` 每项：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pageId` | string | ✅ | 引用 `pages[].id` |
| `state` | string | ✅ | 必须是该页 `states` 里的一个（I12） |
| `label` | string | ⭕ | 这一步的客户可读说明 |

### 场景 ≠ 笛卡尔积

**「每页 × 每状态 × 每组件状态」的遍历是错误做法。** 一个场景 = 业务上真实会发生的
一条路径：空态只在「首次无数据」是真实业务场景时才演示，错误态只在对应校验规则真实
存在时才演示，组件状态分主场景与边际场景、随业务场景成组出现，不单独遍历。

这条纪律不靠人自觉，靠两个字段门禁化：`source` 必填（**写不出编号，就说明这个场景
没有上游依据**），`steps[].state` 必须落在该页声明的 `states` 里（业务上不存在的状态
组合**根本写不出来**）。

### source 与 title 是两种受众

- `source` 是**内部**的：追溯用，回答「这个场景凭什么存在」。只进设计注释文档
- `title` 是**给客户看的**：`console.html` 上渲染的就是它，所以不能出现 `FR-05` 这类编号

这里的取向是：**用编号本身去划「哪些字能出现在客户面前」的界，比维护一张禁用词表可靠**。
编号是 PM 语言里最容易漏出去的标记，而且它有固定格式、可机器判定（I12 用
`(?<![A-Za-z])(?:FR|AC|BR|SM|UC)-\d` 判）。左界用 `(?<![A-Za-z])` 而不是 `\b`：
Python 的 `\b` 把中日韩字符也算「词字符」，「基础积分达上限AC-05-3」这种编号**紧跟
中文**的写法在 `\b` 下会漏网。同理，页面正文层的其它 PM 词由
`check_demo_separation.py` 的禁用词表兜底——**并且它查原始文本，先剥注释再查
等于把「用注释藏起来」放行**。

---

## 不变条件（jf-validate 逐条校验）

| # | 条件 | 级别 |
|---|---|---|
| I1 | `page.id` 与 `page.file` 的 basename 必须相等 | ERROR |
| I2 | `relations[].from/to` 必须引用已存在的 `page.id` | ERROR |
| I3 | `nav: sub-flow` 的页必须有非空 `hostPageId`，且宿主页 `nav` 为 `standalone` | ERROR |
| I4 | 所有 ID 只用小写字母、数字、连字符，且集合内唯一 | ERROR |
| I5 | `device` ∈ {desktop, mobile}；`viewport` 宽高为正整数 | ERROR |
| I6 | 每个 `modules[].id` 至少被一个 page 引用 | ERROR |
| I7 | `crud` 含 `D` 时必须写 `crudNote`（业务替代动作），不写物理删除 | ERROR |
| I8 | 每个 page 的 `states` 非空且包含 `default` | ERROR |
| I9 | `components[].usedBy` 引用的 page 必须存在 | ERROR |
| I10 | `type: route` → 目标 `frame: route`；`type: modal` → 目标 `frame: modal` 且 `hostPageId == from` | ERROR |
| I11 | `design` 块：必须是对象；声明的每个字段是非空字符串且指向**真实存在的文件**；只有 `tokens`/`components` 而无 `spec`/`states` 时提醒徽标挂不上；含未知字段 | 类型错/空值 ERROR；**文件缺失与两类提醒 WARN（`--strict` 转 ERROR）** |
| I12 | `scenes[]` 声明后：每项 `source` 非空、`title` 不含 FR/AC/BR/SM/UC 编号、`moduleId` 引用存在的 module；`steps[]` 非空且每步 `pageId` 引用存在的 page、`state` ∈ 该页 `states` | ERROR |
| F1 | `pages[].file` 指向的文件不存在 | WARN（`--strict` 转 ERROR） |
| F2 | HTML 内 `data-nav` 指向不存在的页面 | ERROR |
| F3 | 跳转链接与 `relations[]` **双向一致**：声明了 relation 但源页（或宿主页）HTML 无对应链接，或页面链接指向了未声明的跳转（侧边导航与「由谁激活」宿主回链属结构性链接，豁免） | WARN（`--strict` 转 ERROR） |
| F4 | 标注 `target` 无法在对应页面 HTML 中定位到元素；或 target 违反协议（`nth-child` / 显示文案 / 非 `#id` 与 `[data-annotation-anchor=值]` 形式） | ERROR（页面未渲染时 WARN，`--strict` 转 ERROR） |

**I11 是唯一一条分级的不变条件**（I1–I10 与 I12 全是 ERROR）。理由：`design` 块声明的文件
**未落盘是常态**——先定契约后补图是正常节奏，那时渲染器降级（不挂设计基线徽标、
组件页只出骨架），链路不阻塞。但「降级」与「路径写错」在产物上长得一模一样：
两种情况下页面都不挂徽标。所以校验器在**未渲染时给 WARN**（提示而非拦截），
在 `--strict`（出图后的门禁，见 F1）下转 **ERROR**——那时「路径写错」必须被拦下。
逐字段的「必须有」**不设**：`tokens`/`components` 是产品自带就复用、不自带就用内置的
资产，缺了是正常形态；只有 `spec`/`states` 一个都没有时才多提醒一句——渲染器判
「接上了设计基线」看的正是这两份文档，都没有意味着徽标永远挂不上。

F1 与 I11 的分工：**F1 管页面文件在不在，I11 管 `design` 声明的四个文件在不在**。
两者都靠 `--strict` 把「提示」升级成「拦截」——`--strict` 的语义就是**出图后的门禁**，
同一个 WARN 渲染前可以放过、渲染后不能。

S0 另含 `annotations[].status` 的词表校验（三态见上文，缺省合法），
以及同一页内 `annotations[].id` 的唯一性校验（气泡 id 由它派生）。

**I12 不分级**：I11 之所以要在「未渲染」与「出图后」两种强度之间切换，是因为
「先定契约后补图」是正常节奏，路径写错与尚未落盘在产物上分不开。`scenes[]` 没有
这个性质——它全是 manifest 内部的自洽（引用存不存在、状态在不在该页声明的表里、
来源写没写），**不依赖任何文件是否落盘**，所以写错了就是写错了，一律 ERROR。
它也是唯一一条**校验「内容凭什么存在」而不是「结构对不对」**的不变条件。

**F4 管到哪为止**：F4 校验的是「渲染器输出与 manifest 自洽」——
manifest 里写的 target，产物里能找到对应元素。判定就是**字符串查找**：
页面里出现 `id="btn-create"` 就算命中。所以「这条标注是否落在**真实业务
元素**上」它判不了——`#btn-create` 与一个恰好同名的占位元素在字符串层面
没有区别，未落点条目带的那个锚点照样能让 F4 过（那是有意为之：未落点
不该让合法 manifest 判失败）。这个落差由**渲染器的未落点 WARN** 暴露，
见上文「气泡协议」——各管一段，不要指望 F4 兜住它。

---

## 跳转协议

```html
<a href="./demand-detail.html" data-nav="demand-detail">查看详情</a>
```

原生 `href` 保证原型脱离任何工具也能跳转；`data-nav` 让渲染器/底座同步当前页。
弹窗同理，点击时由页面内 JS 拦截为浮层，JS 未加载时退化为整页跳转。

---

## ID 命名规则

- 只用 `[a-z0-9-]`，段间用连字符：`demand-list`、`demand-material-upload`
- 页面 id = HTML basename，禁止中文、下划线、大写
- 关系 id 以 `r-` 开头，标注 id 以 `a-<pageId>-` 开头，组件 id 用功能名
- 页面 id 建议以模块 id 为前缀，保证跨模块不撞

---

## 字段映射：jf-ia 文档表 → manifest

| jf-ia 来源 | manifest 字段 |
|---|---|
| BO 第 5 步「主管理对象」 | `pages[].obj` |
| PS「CRUD」列 | `pages[].crud` / `crudNote` |
| PS「导航归属」列（standalone / sub-flow ←宿主） | `pages[].nav` / `hostPageId` |
| LT「页面框架」列（route 全幅 / modal 弹窗 + hostPageId） | `pages[].frame` / `hostPageId` |
| PS「HTML 文件名」列 | `pages[].file`（basename 即 id） |
| PS「承载 FR」列 | `pages[].fr` |
| NM 行（源页面/源元素/类型/目标/触发条件） | `relations[]` 的 from / label / type / to / condition |
| NM 节标题「对象 CRUD 主线」 | 落在 `semantic`：CRUD 链为 `drill`，回退为 `back`，其余为 `rel` |
| FA 功能架构的领域 | `modules[]` |

判定顺序：**先定 nav（能不能直达），再定 frame（NM 类型列），两者不一致即为缺陷**。

> 追溯（jf-interview，#141）：`shaping/07-open-questions.md` 中未拍板的待确认，
> 按其「影响页面」落到对应 `pages[].note`（前缀 `待确认:`，附拍板人与阻塞项）；
> 影响整个模块的，挂到该模块全部页面的 `note`，使待确认能从访谈一路追到 manifest。

---

## 完整示例

```json
{
  "schemaVersion": 1,
  "product": {
    "name": "XX系统",
    "type": "Web",
    "source": { "mrd": "docs/x-mrd.md", "prd": "docs/x-prd.md" }
  },
  "design": {
    "tokens": "prototypes/shared/tokens.css",
    "components": "prototypes/shared/components.js"
  },
  "modules": [
    { "id": "demand", "title": "需求管理", "kind": "prd", "navNumber": "01" }
  ],
  "pages": [
    {
      "id": "demand-list",
      "title": "需求列表",
      "moduleId": "demand",
      "file": "prototypes/pages/demand-list.html",
      "kind": "list",
      "nav": "standalone",
      "frame": "route",
      "obj": "需求项目",
      "crud": "R",
      "device": "desktop",
      "viewport": { "width": 1440, "height": 900 },
      "states": ["default", "empty", "loading", "error"],
      "hostPageId": null,
      "fr": ["FR-05"],
      "ac": ["AC-05-1"]
    },
    {
      "id": "demand-upload",
      "title": "材料上传",
      "moduleId": "demand",
      "file": "prototypes/pages/demand-upload.html",
      "kind": "form",
      "nav": "sub-flow",
      "frame": "route",
      "obj": "材料",
      "crud": "C",
      "hostPageId": "demand-detail",
      "device": "desktop",
      "viewport": { "width": 1440, "height": 900 },
      "states": ["default", "error"],
      "fr": ["FR-11"]
    }
  ],
  "relations": [
    {
      "id": "r-list-detail",
      "from": "demand-list",
      "to": "demand-detail",
      "label": "查看详情",
      "type": "route",
      "semantic": "drill",
      "trigger": "[data-nav=demand-detail]",
      "condition": "行点击"
    }
  ],
  "components": [
    { "id": "page-shell", "title": "页面外壳", "usedBy": ["demand-list", "demand-detail"] }
  ]
}
```
