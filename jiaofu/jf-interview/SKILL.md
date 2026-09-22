---
name: jf-interview
description: 访谈·shaping 门禁——MRD 之后、PRD 之前的产品设计访谈。触发：讨论需求、聊聊、拿不准、待确认、拍板、口径冲突、MVP 边界、shaping。
---

# 访谈门禁（shaping）

jf-mrd 把**业务事实**盘问清楚了，但**产品设计**还没有被讨论过：用户旅程的分支、
首屏放什么、空态长什么样、并发编辑怎么办、万级数据怎么分页——这些在 MRD 里是 `[待确认]`，
到 jf-ia 推导页面时 agent 只能猜，猜错就一路错到 HTML。

本 skill 是 jf-mrd 之后、jf-prd 之前的**访谈门禁**：用有节奏的追问把产品设计的不确定性
收敛成 `shaping/` 8 件套，门禁 G1–G7 全过才移交 jf-prd。
本 skill 只做**编排、契约、门禁**——访谈执行可外包给外部 skill（见「执行外包」），
产物契约不变；没配外部 skill 时由本 skill 自行主持，配了就以它为准——调用失败即**硬失败**，不降级。

## 入口纪律

**正常路径**：由 `jf-prd` 在第 1 步调用。
**独立路径**：用户显式指名时可直接调用——此时先走 `jf-router` 判跨拍。

**典型误入**：

- 想「整理业务事实/规则/状态机」→ `jf-mrd`（盘问已经发生了什么）
- 想「拆 FR / 写 AC」→ `jf-prd`（8 件套过门禁后才移交）
- 想「校验 manifest / 原型对不对」→ `jf-validate`

## 与 jf-mrd 的分工（不重叠）

| | jf-mrd | jf-interview（本 skill） |
|---|---|---|
| 盘问对象 | 业务事实——**已经发生了什么** | 产品设计——**要做什么、用户看到什么** |
| 典型问题 | 角色/实体/流程/规则/状态 | 旅程分支/空态/首屏/权限表现/数据量级 |
| 产物 | MRD 9 块（含 DR 决策记录） | `shaping/` 8 件套 + 待确认清单 |

## 流程

```
intake（读上游 MRD，盘点 [待确认] 与 DR 待拍板项）
  ↓
逐件产出 shaping 8 件套（访谈穿插其间，按「访谈节奏」执行）
  ↓
门禁自检：python3 products/jiaofu/jf-interview/scripts/check_shaping.py <shaping目录>
  ↓
G1–G7 全过 → 移交 jf-prd
任一未过 → 按报错补访谈/补产物，重跑门禁
```

进入条件（满足其一）：MRD 存在 `[待确认]`；MRD 有 DR 待拍板项；用户想讨论需求或定 MVP 边界。

### 产物：`shaping/` 8 件套

```
shaping/
├── 00-intake.md          原始输入与来源（一句话问题 + 上游 MRD 路径）
├── 01-problem.md         问题定义（谁、什么场景、现在怎么解决、为什么不够）
├── 02-users.md           目标用户与角色（对齐 MRD 的 BRO）
├── 03-journey.md         用户旅程（主路径 + 分支，分支必须写明「用户看到什么」）
├── 04-scope.md           MVP 边界：做 / 暂缓 / 不做 / 待确认（四分类，逐项点名；
│                         待确认每条标 OQ 编号，与 07 对账）
├── 05-flows.md           关键流程（对齐 MRD 的 CP，补充分支与异常）
├── 06-shaped-brief.md    定型摘要（1 页，可给客户看）
└── 07-open-questions.md  待确认清单（每条标注：影响哪些页面 / 谁拍板 / 阻塞什么）
```

逐文件模板、字段要求与 G1–G7 判定细则见 `references/shaping-contract.md`（契约全文）。

## 访谈节奏（本 skill 的灵魂）

1. **一次只问 3–5 个问题**，且必须是当前**最降不确定性的**问题——不是按模板从头问到尾。
2. **每题带推荐答案**：「我倾向于 X，理由是…，你确认还是改？」
   让人做选择题而不是填空题，回答成本降低一个数量级。
3. **能查文档回答的不许问人**：MRD/PRD/代码里已经写了的，直接引用并说明出处。
4. **冲突信息单列**：同一问题两次口径不一致时，把两条原话并列 + 来源 + 时间点，
   登记到 `07-open-questions.md` 交给用户拍板，不自行裁决。
5. **不知道就写 `[待确认: ...]`**，不猜、不补、不自行裁决。

## 追问维度清单（7 类，直接摘用）

| 维度 | 典型追问 |
|---|---|
| 用户旅程缺口 | 每个分支用户看到什么？失败后去哪？能返回吗？ |
| UI/UX | 空态长什么样？首屏放什么？加载多久能忍？断网/弱网（3G 隧道）怎么办？ |
| 边界与错误态 | 网络中断、会话过期、并发编辑同一条、提交失败后数据还在吗？ |
| 数据量级 | 万级数据怎么分页？导出上限？列表默认排序？ |
| 权限 | 谁能看/谁能改？无权限是隐藏还是禁用？ |
| 业务权衡 | 只能做一半时间，砍哪个功能？最不能砍的是哪个？ |
| 集成依赖 | 依赖哪个外部系统？它挂了怎么办？数据从哪来、多久同步一次？ |

## 门禁 G1–G7（不通过不放行到 jf-prd）

| # | 条件 |
|---|---|
| G1 | `shaping/` 8 件套全部存在且非空 |
| G2 | 产品定位可 1–2 句表达（`01-problem.md` 首段，超过 3 句即打回；写成引用块也算首段） |
| G3 | `04-scope.md` 的 MVP 四分类（做/暂缓/不做/待确认）每项至少 1 条，且「待确认」每条都有责任人与影响面 |
| G4 | `03-journey.md` 的每个分支都写明「用户此时看到什么」，不得写「待定」；写了「分支：」却没写成条目块（小标题/行首加粗）同样打回——门禁看不见的分支等于没校验 |
| G5 | `07-open-questions.md` 每条能追溯到页面 id 或 MRD 的 DR 编号；给了 `--manifest` 时必须带上页面 id 且存在于 `manifest.pages[]` |
| G6 | 冲突信息（如两次口径不一致）单列在 `07-open-questions.md`，不自行裁决 |
| G7 | `04-scope.md` 的「待确认」与 `07-open-questions.md` 的编号一一对应（两边编号集合相等、各自不重复） |

```bash
python3 products/jiaofu/jf-interview/scripts/check_shaping.py <shaping目录>        # 中文报告
python3 products/jiaofu/jf-interview/scripts/check_shaping.py <shaping目录> --json # 机读（CI）
python3 products/jiaofu/jf-interview/scripts/check_shaping.py <shaping目录> --manifest <manifest.json>  # G5 交叉校验页面 id（manifest 已存在时加：二次迭代重跑门禁，或首程由 jf-ia 产物自检触发）
python3 products/jiaofu/jf-interview/scripts/check_shaping.py --self-test          # 脚本自检
```

## 待确认的追溯（一路到 manifest）

`07-open-questions.md` 每条待确认标注**影响哪些页面**。未拍板就进 jf-prd/jf-ia 的，
按影响页面落到 manifest 的 `pages[].note`（前缀 `待确认:` + 拍板人 + 阻塞项）；
落法见 `products/jiaofu/jf-contract/references/manifest-schema.md` 的追溯说明。
D-03 这类**直接决定页面增减**的待确认，必须在访谈里顶到用户面前，
不许 agent 在 jf-ia 推导页面时自行裁决。

## 执行外包

| 环节 | jf-* 保留 | 外包执行 | 降级 |
|---|---|---|---|
| 8 件套产物结构 | 结构定义 + G1–G7 门禁 | — | — |
| 访谈执行 | 节奏约束（3–5 问/带推荐答案/不问我能查的） | `write-a-prd`（mattpocock，同源工程 skill 体系）、`interview`（MalekAG 追问库）、`grill-with-docs`（本仓库，有 codebase 时） | 未安装时本 skill 自行主持；最低限走 jf-mrd 自带采集流程 |
| 待确认清单 | 追溯字段（影响页面/拍板人/阻塞项） | — | — |

**外包不改变契约**：外部 skill 主持访谈时，同样必须交出 `shaping/` 8 件套并通过 G1–G7；
只产出一段聊天记录视为未完成。候选全名、安装来源、失败语义见中央登记表
`jf-contract/references/external-skills.md`（S0）——登记以中央表为准，本节不再单独维护。

## 纪律

- **不裁决**：待确认与冲突只登记、只上抛，agent 不替用户拍板
- **先问最降不确定性的**：问题按「阻塞多少页面决策」排序，不按模板顺序
- **不问我能查的**：MRD/PRD/代码里已有的答案，引用出处，不占用提问额度
- **门禁只认产物**：以 `check_shaping.py` 退出码为准，不以「聊过了」为准

## 项目适配

- **目录路径**：`shaping/` 默认与 MRD 同级（如 `docs/shaping/`），位置由项目结构决定
- **MRD 缺失**：允许从一句话问题冷启动（`00-intake.md` 记录来源），移交 jf-prd 前建议先补 jf-mrd
- **上游 DR**：MRD 的 DR 待拍板项逐条进 `07-open-questions.md`，编号沿用（如 `DR: D-03`），不重新编号
