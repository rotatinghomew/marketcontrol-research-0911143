# 控制关系不确定时海鲜市场集中度资料约定

份额的交易分母限所选边界内的已登记成交。多数表决权是控制证据的一类，不代表少数经济权益自动获得控制；joint_agreement 说明共享决策协议，不能任意归到其中一个家族。联合经营是待分析的假设，不改变历史工商证据。时间有效期均为左闭右开，valid_to 为空表示尚无已知终止日。份额集中度是统计量，不是法律裁定。

## 数据表

### `entities`

登记主体身份已确认，无需做概率实体匹配。

| 字段 | 解析类型 |
| --- | --- |
| `id` | `text` |
| `name` | `text` |
| `entity_kind` | `text` |

### `ownership`

voting 为表决权，equity 仅经济权益，joint 须按同协议结合理解；有效期左闭右开，未确认边仅为待核证据。

| 字段 | 解析类型 |
| --- | --- |
| `id` | `text` |
| `parent` | `text` |
| `child` | `text` |
| `share` | `number` |
| `right_kind` | `text` |
| `status` | `text` |
| `valid_from` | `date` |
| `valid_to` | `date?` |
| `joint_agreement` | `text?` |

### `transactions`

已完成成交，品类、鲜冻形态和销地共同描述候选市场边界。

| 字段 | 解析类型 |
| --- | --- |
| `id` | `text` |
| `entity_id` | `text` |
| `day` | `date` |
| `species` | `text` |
| `form` | `text` |
| `region` | `text` |
| `amount` | `money` |
| `weight_kg` | `number` |

### `coverage`

覆盖声明不等于可推算的全市场总额，unknown 代表缺少外部交易基准。

| 字段 | 解析类型 |
| --- | --- |
| `id` | `text` |
| `period` | `text` |
| `region` | `text` |
| `coverage_kind` | `text` |
| `known_amount` | `money?` |
| `note` | `text` |

## 文件和数值语义

空单元格只在带问号的类型中表示缺失；零和空值不同。金额由十进制定点字符串保存，浮点数仅用于探索性统计。所有数据均为本地生成的虚构经营记录，不对应真实公司、客户或住址。数值剖面只反映观察数据，不能代替总体推断。

研究备注的参数为业务自由对象，不代表已执行了任何统计模型。原始表与已有视图可单独查询。
