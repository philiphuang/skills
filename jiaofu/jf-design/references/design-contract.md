# 设计基线契约（DESIGN.md + components-and-states.md）

> jf-design 的两个契约文件的**唯一权威模板**：结构、必含段落、硬规则。
> 校验实现：`products/jiaofu/jf-design/scripts/check_design.py`（门禁 G1–G8）。
> 消费方：`jf-uxprompt` 渲染器（读 `manifest.design` 优先复用外部基线）。

设计基线是 jf-* 链路上的一等产物，在 jf-ia 之后、jf-wireframe 之前定稿：

| 文件 | manifest.design 字段 | 角色 |
|---|---|---|
| `DESIGN.md` | `spec` | 三层 token 契约，`tokens.css` 的真相源 |
| `components-and-states.md` | `states` | 组件×状态契约，展示页 `components.html` / `states.html` 的数据源 |
| `prototypes/shared/tokens.css` | `tokens` | 由 DESIGN.md 派生的落地 CSS（与 DESIGN.md 同源） |

路径相对 manifest 所在目录。

---

## 一、DESIGN.md 模板

```markdown
# DESIGN.md — <产品名> 设计基线

> 三层 token：primitive → semantic → component。
> 硬规则：semantic / component 层禁止裸值，只能引用上一层。
> 本文件是 prototypes/shared/tokens.css 的真相源。

## 产品基调

<一段话：目标用户、行业气质、品牌约束、想给客户的整体感受。
不要写成功能清单——只回答「这套界面看上去应该像什么」。>

## 色板（primitive）

> 裸值（hex）只允许出现在这一层。

| token | 值 | 用途 |
|---|---|---|
| `blue-600` | `#2563eb` | 主操作 / 链接 |
| `gray-900` | `#1f2328` | 主文本（带冷色调的黑，不用纯黑） |
| `gray-050` | `#f7f8fa` | 页面底色 |

## 字体与字阶

| token | 值 | 用途 |
|---|---|---|
| `font-ui` | `-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif` | 界面字体 |
| `text-body` | `14px / 1.6` | 正文 |
| `text-title` | `22px / 600` | 页标题 |

## 间距 / 圆角 / 阴影栅格

| token | 值 | 用途 |
|---|---|---|
| `space-4` | `16px` | 常规内边距 |
| `radius-md` | `6px` | 卡片 / 输入圆角 |
| `shadow-card` | `0 1px 2px rgba(31,35,40,.06)` | 卡片投影 |

## 语义变量（semantic）

> 只能引用 primitive 表中的 token 名；**禁止裸 hex**（G2 扫描 `#xxx`）。

| 变量 | 引用 | 用途 |
|---|---|---|
| `--jf-accent` | `blue-600` | 主强调色 |
| `--jf-text` | `gray-900` | 主文本 |
| `--jf-bg` | `gray-050` | 页面底色 |

## 组件变量（component）

> 只能引用 semantic 变量；**禁止裸 hex / 随意 px**。

| 变量 | 引用 | 用途 |
|---|---|---|
| `--jf-btn-bg` | `--jf-accent` | 主按钮底色 |
| `--jf-table-row-h` | `--jf-space-4` | 表格行高基准 |

## 明确排除项

- 禁用字体 Inter / Roboto / Arial / Space Grotesk（被 AI 用烂，一眼假）
- 禁灰字配彩底（对比度不足）
- 禁纯黑灰不带色调（要带冷/暖倾向）
- 禁卡片套卡片（层级用间距和分隔线表达）
- 禁 bounce / elastic 缓动（用 ease / ease-out）
```

### 必含段落（G1 逐项校验）

| 段落 | 识别关键词（标题行内） |
|---|---|
| 产品基调 | `基调` |
| 色板（primitive） | `色板` 或 `primitive` |
| 字体与字阶 | `字体` 或 `字阶` |
| 间距 / 圆角 / 阴影栅格 | `间距` / `圆角` / `栅格` |
| 语义变量（semantic） | `语义变量` 或 `semantic` |
| 组件变量（component） | `组件变量` 或 `component` |
| 明确排除项 | `排除` |

### 三层硬规则（G2）

```
primitive  →  semantic  →  component
#2563eb      --jf-accent   --jf-btn-bg
（裸值）       （只引用名）    （只引用变量）
```

| 层 | 允许 | 禁止 |
|---|---|---|
| primitive | 裸 hex、px、字体栈 | — |
| semantic | 只引用 primitive token 名 | 裸 hex（脚本扫 `#[0-9a-fA-F]{3,8}`） |
| component | 只引用 semantic 变量 | 裸 hex、随意 px |

三层各自至少一行表数据（「三层结构完整」）。

### tokens.css 落地一致（G7）

`DESIGN.md` 是真相源，`tokens.css` 是它的落地——两边不一致时以 DESIGN.md 为准，
但门禁必须把不一致**报出来**。没有这道检查时，把主强调色改成任意色相、
在 primitive 里塞个没声明过的变量，G1–G6 一律全绿：真相源名存实亡。

G7 逐条比对 `manifest.design.tokens` 指向的文件：

| 检查 | 说明 |
|---|---|
| 漂移 | CSS 变量的值 ≠ DESIGN.md 同名 token 的值（字号 / 间距 / 色值任何一处） |
| 未声明的裸值 | primitive 层出现了 DESIGN.md 里没有的变量 |
| 未声明的语义/组件变量 | semantic / component 层出现了 DESIGN.md 里没有的变量 |
| 引用漂移 | `var(--jf-x)` 里的 x 与 DESIGN.md 该行「引用」列写的不一致 |
| 越级 | component 直接引用 primitive，或 semantic 引用 component |
| 断链 / 环 | `var()` 指向不存在的变量，或 a→b→a 互相引用 |

层由**取值形态**推断，不靠位置：整串就是一个 `var()` → 比它引用的变量低一层；
否则按 primitive 处理。所以三层可以写在同一个 `:root` 里，也可以分三个 `:root`。

DESIGN.md 侧的名字不带 `--jf-` 前缀（`blue-600` / `font-ui` / `space-4`），
CSS 侧带（`--jf-blue-600`）——比对时统一成变量名。primitive 分散在
**色板 / 字体与字阶 / 间距·圆角·栅格**三个段落，三处都是合法来源。

### 引用 token 可解析（G8）

「组件×状态」表的 `引用 token` 列不是自由文本，门禁会核对：

- **具名 token**（`--jf-btn-bg`）→ 必须在 `tokens.css` 里存在，否则 ERROR。
- **族通配**（`--jf-table-*`）→ 必须至少命中一个变量，否则 WARN。

分两档是因为两类声明的性质不同：具名是「事实」（写了就得有），
族是「归类」（占位性质的 `--jf-shell-*` 在模板里合法，拦死会把模板本身判死，
但空命中往往意味着族名改了，值得提示）。

---

## 二、components-and-states.md 模板

```markdown
# components-and-states.md — <产品名> 组件×状态契约

> 每个组件一行，四态齐全；跨模块五状态必须定义。
> id 列必须能追溯到 manifest.components[].id（jf-ia 已定组件，本文件补状态不增删）。

## 组件×状态

| 组件 | id | 类型 | default | hover | active | disabled | 其他状态 | 引用 token | usedBy |
|---|---|---|---|---|---|---|---|---|---|
| 页面外壳 | `page-shell` | 容器 | ✓ | — | — | — | — | `--jf-accent-line`、`--jf-bg` | demand-list, demand-detail |
| 数据表格 | `data-table` | 容器 | ✓ | — | — | — | loading/empty/error | `--jf-skeleton`、`--jf-border` | demand-list |
| 主操作按钮 | `primary-button` | 交互 | ✓ | ✓ | ✓ | ✓ | — | `--jf-btn-bg`、`--jf-btn-bg-hover` | demand-list |

容器类组件的四态落点写在这里（**标 `—` 就必须写**，门禁按 id 逐条核对）：

- `page-shell`：hover 落在左侧导航项（底色转灰）；active 落在当前导航项（强调浅底 + 加粗）；disabled 落在无权限时的导航项灰化、不可点。
- `data-table`：hover 落在行（底色转页面底色）；active 落在当前打分行（强调浅底）；disabled 落在专家提交后单元格只读。

## 跨模块状态

> 五个状态全部定义；漏一个就是一次返工（评审时最常被问、也最常被漏）。

| 状态 | 触发场景 | 视觉表现 | 文案口径 | 落点组件 |
|---|---|---|---|---|
| `empty` | 列表 / 详情无数据 | 居中插画 + 主操作引导 | 「暂无XX」+ 引导文案（与业务方确认） | `data-table` |
| `loading` | 数据获取中 | 骨架屏 | 不出文案 | `data-table` |
| `error` | 请求失败 | 错误条 + 重试按钮 | 「加载失败，请重试或联系管理员」 | `data-table` |
| `disabled` | 无操作权限 | 控件降透明度 + 禁指针 | 不出文案（tooltip 说明原因） | `page-shell` |
| `permission-denied` | 无页面访问权限 | 整页无权限卡 | 「无访问权限，请联系管理员开通」 | `page-shell` |
```

### 契约规则

| 规则 | 门禁 |
|---|---|
| `类型` 列取值只能是 `交互` / `容器` | G3 |
| **交互**组件四态（default/hover/active/disabled）全部 `✓` | G3 |
| **容器**组件四态可标 `—`，但表下必须有以 `- \`<id>\`：` 开头的落点说明 | G3 |
| 跨模块五状态（empty/loading/error/disabled/permission-denied）全部定义 | G4 |
| `id` 列（去反引号）⊆ `manifest.components[].id`；反向缺漏给 WARN | G5 |
| `引用 token` 列写的每个具名 token 都必须在 `tokens.css` 里存在 | G8 |
| `usedBy` 列与 manifest `components[].usedBy` 对齐（逗号分隔页面 id） | 人工核对 |

四态标记只认 `✓`（`✔` / `✅` 等价）；`—` 或留空视为缺失——**容器除外**，容器的
`—` 是「状态落在子部件上」的正经写法，代价是必须补落点说明。

`类型` 列留空的按 `交互` 处理（向后兼容早期只写四态的文件）。

落点说明的写法：表下以 `- \`<id>\`：<说明>` 开头的一行，一个组件一行。
`check_design.py` 只核对该行**存在**，内容是否说得通由人工评审——
门禁能把「忘了写」拦住，拦不住「写得不对」。

---

## 三、三层 token 示例（完整链）

```css
/* tokens.css —— 由 DESIGN.md 派生，三层同文件分层声明 */

/* primitive：唯一允许裸值的一层 */
:root {
  /* …color / font / space / radius / shadow 原始值… */
}

/* semantic：只引用 primitive */
:root {
  --jf-accent: var(--jf-blue-600);
  --jf-text: var(--jf-gray-900);
  --jf-bg: var(--jf-gray-050);
}

/* component：只引用 semantic */
:root {
  --jf-btn-bg: var(--jf-accent);
  --jf-table-row-h: var(--jf-space-4);
}
```

primitive 层在 CSS 里可用 `--jf-blue-600: #2563eb;` 形式落地，
semantic 层用 `var()` 引用，component 层再引用 semantic——三层在 CSS 中同样不越级。

---

## 四、反模式清单（视觉评审门禁）

> 摘自 impeccable 61 条确定性反模式 + anthropics/frontend-design 官方基线。
> 评审时逐条核对；出现在产物里即打回。

| # | 反模式 | 为什么 |
|---|---|---|
| 1 | Inter / Roboto / Arial / Space Grotesk 字体 | 被 AI 用烂，一眼假；选有性格的字体栈 |
| 2 | 灰字配彩底 | 对比度不足，可读性差 |
| 3 | 纯黑（`#000`）/ 无色调灰阶 | 要带冷 / 暖倾向，色板里写明 |
| 4 | 卡片套卡片 | 层级用间距和分隔线表达，不嵌套容器 |
| 5 | bounce / elastic 缓动 | 动效用 ease / ease-out，克制 |
| 6 | 全部等宽对称布局 | 留非对称与留白节奏 |
| 7 | 渐变 / 阴影堆砌 | 每页最多一个主视觉层次 |
| 8 | 无障碍当装饰 | 触控目标 ≥44px、对比度过 WCAG AA 是 CRITICAL |

G6 只机器校验「排除项写了且够具体」（≥2 条且提及字体 / 配色套路）；
全部 8 条由人工评审或 `impeccable critique` / `audit` 核对。

---

## 五、降级方案（外部 skill 未安装时）

无 `ui-ux-pro-max:design-system` / `impeccable` 时，按本模板手工产出两份契约文件：

1. `DESIGN.md`：按第一节模板填——primitive 直接用内置简洁单色规范的值起步
   （`render_manifest.py` 内置 tokens.css 的色板可作 primitive 初稿）
2. `components-and-states.md`：按第二节模板，从 `manifest.components[]`
   生成骨架行，逐格补 `✓` 与跨模块五状态
3. 跑 `python3 products/jiaofu/jf-design/scripts/check_design.py manifest.json` 过 G1–G8

降级不改变契约：手工产物与外部 skill 产物走同一道门禁。
