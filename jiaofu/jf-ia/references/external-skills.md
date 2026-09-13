# jf-ia 执行外包登记表

> 登记本 skill 各块的**外部执行者**：候选 skill / 安装命令 / 输入 / 期望产出 / 门禁 / 降级方案。
> 调研依据：`research/jf-prd-skill-benchmark-report.md`（候选 C2 `pbakaus/impeccable`、A1 `comeonzhj/interaction-prd` 的评级与理由）。
> 本文件是 `SKILL.md`「项目适配 · 执行外包」那条的落地清单。

三条纪律（对所有外包点一律适用）：

1. **外包不改变契约**：外部执行者做完，照样要交出同一份产物、过同一道门禁。jf-* 只管编排和门禁，谁做的无所谓。
2. **只交文档表视为未完成**：IA 的产物是 `manifest.json`，不是漂亮的表格。表格必须同时落成 manifest 并过校验（映射规则见 `products/jf-contract/references/manifest-schema.md`）。
3. **未安装即降级**：候选一个都没装时本 skill 自行执行，链路不阻塞——这是默认路径，不是异常路径。

## 外包点：PS → LT → NM → FA（信息架构四块）

产出 `manifest.json` 的骨架（`modules` / `pages` / `relations`），是下游⑤线框与⑥生成的唯一输入。四块串行，任一候选都只能整体接手，不能只做一块。

| 候选 skill | 安装命令 | 输入 | 期望产出 | 门禁 | 降级方案 |
|---|---|---|---|---|---|
| `impeccable`（`/impeccable shape`）——**在写代码之前先规划 UX/UI**，正好补 PRD 与页面之间的那一环 | Claude Code：`/plugin marketplace add pbakaus/impeccable` → `/plugin` 里安装；或项目根跑 `npx impeccable install`（`--providers=claude`、`--scope=project\|global`）；升级 `npx impeccable update` | ②PRD（FR/AC/RP/PP）+ ①用户旅程；本 skill 的 PS/LT/NM 表头作为输出模板 | UX/UI 规划稿（信息分组、页面层级、导航路径、页面归属），由本 skill 转写为 PS/LT/NM 三张表 | `python3 products/jf-validate/scripts/validate_manifest.py <manifest> --strict` 退出码 0（I1–I12 + F1–F4 全过，WARN 也计入失败） | 本 skill 自行跑 PS→LT→NM→FA 四块，产出同构的表 + `manifest.json` |
| `ux-strategy:information-architecture`（Owl-Listener/designer-skills）——现成 IA 工作流 | `/plugin marketplace add Owl-Listener/designer-skills` → `/plugin` 里安装（以该仓库 README 为准） | 同上 | 站点地图 / 页面清单 / 导航层级 | 同上。产出必须能整表映射到 `pages[]`（`nav` / `hostPageId` / `frame` 三列不许留空或猜） | 同上 |
| `card-sorting`（Owl-Listener/designer-skills）——LT/NM 两块的分组与命名可单独外包 | 同上 | ②PRD 的功能清单（FR）+ 用户角色 | 卡片分组结果（分组名 + 归属卡片 + 分歧点） | 同上。分组结果只决定 LT/NM 的表内容，**不豁免 manifest 校验**；分歧点单列不自行裁决 | 本 skill 按 FR 归属与业务对象自行分组 |

## 接入细则

**外部产出 → manifest 的映射**（外包方交表格时的转写入口）：

| 外部产出 | manifest 落点 | 关键判定 |
|---|---|---|
| 页面清单 / 站点地图 | `pages[]` | `nav`：可独立路由 → `standalone`；只在宿主页上下文中出现 → `sub-flow`（必须带 `hostPageId`） |
| 导航层级 / 分组 | `modules[]` + `pages[].moduleId` | 侧边导航只列 `standalone` 页，分组即 module |
| 跳转表 | `relations[]` | `type`：`route` / `modal` / `external`；`semantic`：`drill` / `back` / `rel` / `activate` |
| 组件清单 | `components[]` | 只登记 id 与 usedBy，**状态在 jf-design 的 `components-and-states.md` 里补齐**，本 skill 不增删组件 |

**共同门禁**（无论谁执行都要跑）：

```bash
python3 products/jf-validate/scripts/validate_manifest.py <manifest> --strict
```

**降级自检**：不装任何候选时，本 skill 的四块流程与上面「期望产出」完全同构——外包只是换执行者，不换产物形状。
