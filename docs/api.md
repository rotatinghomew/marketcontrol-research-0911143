# 资料服务接口

服务只在本机提供 JSON，响应编码为 UTF-8。查询接口不修改资料。

| 方法和路径 | 当前行为 |
| --- | --- |
| `GET /health` | 数据指纹和存活状态 |
| `GET /tables` | 表、字段类型和记录数 |
| `GET /tables/{name}?offset=0&limit=50` | 原始资料分页；偏移非负，每页一至五百行 |
| `GET /view` | 当前领域经营资料摘要 |
| `GET /profiles` | 数值字段的观察数、缺失数、中位数及绝对中位差 |
| `POST /cases` | 保存研究备注和当前完整资料副本；返回新记录 |
| `GET /cases` | 研究记录索引 |
| `GET /cases/{id}` | 校验完整性并回读记录 |
| `POST /research/control` | 按生效期与证据类型形成可解释经营主体分组 |
| `POST /research/concentration` | 市场边界、份额集中度、情景区间与联合经营试算 |

创建研究备注的字段为 `label`、`options` 和 `notes`，分别是名称、参数对象与说明文字。名称一至一百二十字，后两项可省略。不接受其他字段，不允许覆盖旧记录。记录 ID 由服务生成。资料指纹由原始数据和结构共同形成，不表示计算结果的统计可信度。

## 集中度研究接口

两个研究接口均为只读 POST，请求体必须是 JSON 对象，未知字段返回 400，不修改任何资料。

### `POST /research/control`

请求字段：

| 字段 | 含义 |
| --- | --- |
| `as_of` | 认定时点，`YYYY-MM-DD`；省略时取当天 |
| `include_unconfirmed` | 是否在显式假设下纳入 `unconfirmed` 边，默认 `false` |
| `joint_policy` | `independent`（默认，共同控制企业保持独立）或 `joint_group`（按同一 `joint_agreement` 合并） |

响应给出每个经营主体的成员、表决权根主体、间接控制路径上的证据边 ID、共同控制协议标识，以及交叉持股提示。`ambiguous_edges` 逐条说明被排除边的原因（`unconfirmed`、`expired`、`equity_only`、`joint_independent_policy`）和改判后会合并哪些组。`equity` 经济权益边在任何假设下都不产生控制连通。

### `POST /research/concentration`

请求字段：

| 字段 | 含义 |
| --- | --- |
| `boundary` | `period`（`YYYY-MM` 简写）或 `period_from`/`period_to`；可再按 `species`、`forms`、`regions` 数组过滤 |
| `scenario` | 与控制接口相同的三个字段，作为基线假设 |
| `joint_operation` | 可选，参与联合经营假设的登记实体 ID 数组，至少涉及基线中的两个经营主体 |

响应要点：

* `coverage` 按期间与地区对照覆盖声明；`unknown` 表示缺少外部交易基准，`external_benchmark_available` 为假时分母只能是边界内已登记成交，`is_whole_market` 恒为假。
* `baseline_concentration` 同时给出金额与重量两个口径的 CR1、CR4、HHI（点数），`ranking` 中每个经营主体可按 `members` 拆回原登记主体的金额、重量与组内贡献。
* `scenario_range` 在四个显式假设（是否纳入未确认边 × 两种共同控制策略）下分别计算，并给出每个指标的最小值、最大值及其对应假设；`decision_changing_edges` 点名是哪些边的改判导致了分组与指标变化。
* `joint_operation` 只在传入时出现，给出合并前后指标、差值与可拆回的成员清单，属于假设试算。
* `caveats` 固定声明分母口径、统计量性质与"不自动给出合法或违法结论"。

边界内没有成交时，CR 与 HHI 返回 `null` 而不是零，避免把"无观察"误读为"无集中度"。

源表未找到或记录 ID 无效返回 404；字段或分页无效返回 400。默认监听 127.0.0.1:8080。服务当前提供资料浏览、数值探索、研究备注与集中度研究，集中度输出是描述性统计与假设情景，不将保存备注或试算结果视为已完成的经营或法律判断。
