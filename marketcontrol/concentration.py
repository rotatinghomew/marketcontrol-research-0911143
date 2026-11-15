"""集中度研究：从有生效期的控制证据到可解释的经营主体与集中度情景。

本模块只做资料整理与统计描述，不做法律定性。关键口径：

* ``voting`` 是表决权控制证据；``equity`` 仅为经济权益，任何假设下都不产生控制连通；
  ``joint`` 必须结合同一 ``joint_agreement`` 理解，不能任意归给其中一方。
* 证据有效期左闭右开：``valid_from <= as_of < valid_to``，``valid_to`` 为空表示尚无已知终止日。
* ``unconfirmed`` 边只是待核证据，基线分组不采用，只能在显式假设下纳入。
* 份额分母始终是所选市场边界内的已登记成交合计；缺少外部交易基准时不得冒充全市场。
* 集中度（CRn、HHI）是统计量，联合经营是假设情景，均不自动给出合法或违法结论。
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")
JOINT_POLICIES = ("independent", "joint_group")
CAVEATS = (
    "份额分母为所选市场边界内的已登记成交合计，不是全市场总额；覆盖声明为 unknown 时不存在外部交易基准。",
    "CRn 与 HHI 是描述性统计量，不构成合法或违法结论，管理方需携带证据另行讨论。",
    "联合经营是假设情景，只用于试算，不改变历史工商登记与控制证据。",
    "百分比与 HHI 在展示层按四舍五入保留两位小数，各主体份额之和可能不严格等于 100。",
)


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------


def quantize(value, places=TWO_PLACES):
    return value.quantize(places, rounding=ROUND_HALF_UP)


def money(value):
    return str(quantize(Decimal(value) if not isinstance(value, Decimal) else value))


def as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def month_bounds(period):
    year, month = (int(part) for part in period.split("-"))
    if not 1 <= month <= 12:
        raise ValueError("月份需为 YYYY-MM 形式")
    start = date(year, month, 1)
    end = date(year + (month // 12), (month % 12) + 1, 1)
    return start.isoformat(), (end - timedelta(days=1)).isoformat()


class UnionFind:
    def __init__(self, nodes):
        self.parent = {node: node for node in nodes}

    def find(self, node):
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != node:
            self.parent[node], node = root, self.parent[node]
        return root

    def union(self, left, right):
        self.parent[self.find(left)] = self.find(right)


# ---------------------------------------------------------------------------
# 证据生效与分类
# ---------------------------------------------------------------------------


def edge_active_at(edge, as_of):
    start = as_date(edge["valid_from"])
    if as_of < start:
        return False
    if edge["valid_to"] is not None and as_of >= as_date(edge["valid_to"]):
        return False
    return True


def classify_edges(ownership, as_of, include_unconfirmed):
    """把证据边按权利类型、确认状态和生效期分类。

    返回的每条边附带 ``exclusion_reason``（仅被排除时），便于逐条解释。
    """
    classified = {"voting": [], "joint": [], "equity": [], "excluded": []}
    for edge in ownership:
        item = dict(edge)
        if not edge_active_at(edge, as_of):
            item["exclusion_reason"] = "expired"
            classified["excluded"].append(item)
            continue
        if edge["status"] != "confirmed" and not include_unconfirmed:
            item["exclusion_reason"] = "unconfirmed"
            classified["excluded"].append(item)
            continue
        kind = edge["right_kind"]
        if kind not in ("voting", "joint", "equity"):
            item["exclusion_reason"] = "unknown_right_kind"
            classified["excluded"].append(item)
            continue
        classified[kind].append(item)
    return classified


def detect_cross_holdings(equity_edges):
    """双向经济权益边构成交叉持股；它只提示关联，不产生控制连通。"""
    directed = {(edge["parent"], edge["child"]): edge["id"] for edge in equity_edges}
    found = []
    seen = set()
    for (parent, child), edge_id in directed.items():
        if (child, parent) in directed:
            key = tuple(sorted((edge_id, directed[(child, parent)])))
            if key not in seen:
                seen.add(key)
                found.append({
                    "entities": sorted((parent, child)),
                    "edge_ids": list(key),
                    "note": "双向经济权益属于交叉持股，仅表明少数参股关系，不作为控制证据。",
                })
    return found


# ---------------------------------------------------------------------------
# 经营主体分组
# ---------------------------------------------------------------------------


def _voting_paths(voting_edges):
    """对每条表决权边保留 parent→child 邻接，供还原间接控制路径。"""
    adjacency = defaultdict(list)
    for edge in voting_edges:
        adjacency[edge["parent"]].append((edge["child"], edge["id"]))
    return adjacency


def _shortest_path(adjacency, roots, target):
    queue = [(root, []) for root in roots]
    seen = set(roots)
    while queue:
        node, path = queue.pop(0)
        for child, edge_id in adjacency.get(node, []):
            new_path = path + [edge_id]
            if child == target:
                return new_path
            if child not in seen:
                seen.add(child)
                queue.append((child, new_path))
    return []


def build_partition(catalog, as_of, include_unconfirmed=False, joint_policy="independent"):
    if joint_policy not in JOINT_POLICIES:
        raise ValueError("joint_policy 仅支持 independent 或 joint_group")
    as_of = as_date(as_of)
    entities = [row["id"] for row in catalog.rows("entities")]
    classified = classify_edges(catalog.rows("ownership"), as_of, include_unconfirmed)

    union = UnionFind(entities)
    joint_agreements = defaultdict(list)
    for edge in classified["joint"]:
        agreement = edge["joint_agreement"]
        if not agreement:
            raise ValueError("joint 证据缺少 joint_agreement 标识：" + edge["id"])
        joint_agreements[agreement].append(edge)
        if joint_policy == "joint_group":
            union.union(edge["parent"], edge["child"])
    for edge in classified["voting"]:
        union.union(edge["parent"], edge["child"])

    components = defaultdict(list)
    for entity in entities:
        components[union.find(entity)].append(entity)

    adjacency = _voting_paths(classified["voting"])
    incoming = {edge["child"] for edge in classified["voting"]}
    voting_parties = {
        entity for edge in classified["voting"] for entity in (edge["parent"], edge["child"])
    }
    groups = []
    for members in sorted(components.values(), key=lambda part: min(part)):
        members = sorted(members)
        roots = sorted(entity for entity in members if entity not in incoming)
        member_evidence = []
        for entity in members:
            path = [] if entity in roots else _shortest_path(adjacency, roots, entity)
            if entity in incoming:
                basis = "voting_chain"
            elif entity in voting_parties:
                basis = "voting_root"
            else:
                basis = "singleton_or_agreement"
            member_evidence.append({
                "entity_id": entity,
                "control_path_edge_ids": path,
                "basis": basis,
            })
        agreement_ids = sorted({
            edge["joint_agreement"] for edge in classified["joint"]
            if edge["parent"] in members or edge["child"] in members
        })
        groups.append({
            "group_id": "",  # 排序后统一编号
            "members": members,
            "voting_roots": roots,
            "joint_agreement_ids": agreement_ids,
            "member_evidence": member_evidence,
        })
    for index, group in enumerate(groups, 1):
        group["group_id"] = f"G{index:02d}"

    cross_holdings = detect_cross_holdings(classified["equity"])
    independent_joint = [] if joint_policy == "joint_group" else classified["joint"]
    return {
        "as_of": as_of.isoformat(),
        "scenario": {
            "include_unconfirmed": include_unconfirmed,
            "joint_policy": joint_policy,
        },
        "effective_edges": {
            "voting": [edge["id"] for edge in classified["voting"]],
            "joint_used": [edge["id"] for edge in classified["joint"]
                           if joint_policy == "joint_group"],
            "joint_held_independent": [edge["id"] for edge in independent_joint],
            "equity_not_control": [edge["id"] for edge in classified["equity"]],
        },
        "joint_agreements": {
            agreement: sorted({edge["parent"] for edge in edges} | {edge["child"] for edge in edges})
            for agreement, edges in sorted(joint_agreements.items())
        },
        "cross_holdings": cross_holdings,
        "groups": groups,
        "excluded_edges": classified["excluded"],
    }


def _group_lookup(groups):
    mapping = {}
    for group in groups:
        for entity in group["members"]:
            mapping[entity] = group["group_id"]
    return mapping


def edge_effects(partition, ownership):
    """说明每条未参与当前分组的边若改判，会合并哪些组。"""
    by_id = {edge["id"]: edge for edge in ownership}
    groups = partition["groups"]
    lookup = _group_lookup(groups)
    effects = []
    for edge in partition["excluded_edges"]:
        endpoints = (edge["parent"], edge["child"])
        current = sorted({lookup[entity] for entity in endpoints})
        would_merge = len(current) > 1
        effects.append({
            "edge_id": edge["id"],
            "parent": edge["parent"],
            "child": edge["child"],
            "right_kind": edge["right_kind"],
            "status": edge["status"],
            "share": edge["share"],
            "valid_from": edge["valid_from"],
            "valid_to": edge["valid_to"],
            "exclusion_reason": edge["exclusion_reason"],
            "current_groups": current,
            "would_merge_groups": would_merge,
            "effect_note": _effect_note(edge, would_merge),
        })
    for edge_id in partition["effective_edges"]["joint_held_independent"]:
        edge = by_id[edge_id]
        current = sorted({lookup[edge["parent"]], lookup[edge["child"]]})
        effects.append({
            "edge_id": edge_id,
            "parent": edge["parent"],
            "child": edge["child"],
            "right_kind": "joint",
            "status": edge["status"],
            "share": edge["share"],
            "valid_from": edge["valid_from"],
            "valid_to": edge["valid_to"],
            "exclusion_reason": "joint_independent_policy",
            "current_groups": current,
            "would_merge_groups": len(current) > 1,
            "effect_note": "共同控制边在 independent 假设下不归并任何一方；切换 joint_group 假设会按协议合并 "
                           + "、".join(current),
        })
    for edge_id in partition["effective_edges"]["equity_not_control"]:
        edge = by_id[edge_id]
        effects.append({
            "edge_id": edge_id,
            "parent": edge["parent"],
            "child": edge["child"],
            "right_kind": "equity",
            "status": edge["status"],
            "share": edge["share"],
            "valid_from": edge["valid_from"],
            "valid_to": edge["valid_to"],
            "exclusion_reason": "equity_only",
            "current_groups": sorted({lookup[edge["parent"]], lookup[edge["child"]]}),
            "would_merge_groups": False,
            "effect_note": "经济权益边在任何控制假设下都不产生控制连通，改判不会合并经营主体。",
        })
    return sorted(effects, key=lambda item: item["edge_id"])


def _effect_note(edge, would_merge):
    reason = edge["exclusion_reason"]
    if reason == "unconfirmed":
        return ("证据确认后将合并 " + f"{edge['parent']} 与 {edge['child']}" if would_merge
                else "证据即使确认，两端也已在同一经营主体内，分组不变。")
    if reason == "expired":
        return "证据在该时点已过生效期；调整 as_of 使其生效才可能改变分组。"
    return "当前假设下不参与控制分组。"


def control_view(catalog, as_of=None, include_unconfirmed=False, joint_policy="independent"):
    if as_of is None:
        as_of = date.today().isoformat()
    partition = build_partition(catalog, as_of, include_unconfirmed, joint_policy)
    partition["ambiguous_edges"] = edge_effects(partition, catalog.rows("ownership"))
    partition["interpretation"] = (
        "independent：共同控制企业保持独立，协议证据只作提示；"
        "joint_group：同一 joint_agreement 各方显式假设为一个经营主体。"
    )
    return partition


# ---------------------------------------------------------------------------
# 市场边界、覆盖声明与成交汇总
# ---------------------------------------------------------------------------


def parse_boundary(raw, catalog):
    raw = raw or {}
    allowed = {"period", "period_from", "period_to", "species", "forms", "regions"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError("边界条件包含未知字段：" + "、".join(sorted(unknown)))
    transactions = catalog.rows("transactions")
    known_species = sorted({row["species"] for row in transactions})
    known_forms = sorted({row["form"] for row in transactions})
    known_regions = sorted({row["region"] for row in transactions})

    period_from = raw.get("period_from")
    period_to = raw.get("period_to")
    if raw.get("period"):
        if period_from or period_to:
            raise ValueError("period 与 period_from/period_to 不能同时给出")
        period_from, period_to = month_bounds(raw["period"])
    if period_from:
        period_from = as_date(period_from).isoformat()
    if period_to:
        period_to = as_date(period_to).isoformat()
    if period_from and period_to and period_from > period_to:
        raise ValueError("期间起点晚于终点")

    def check_list(field, known):
        values = raw.get(field)
        if values is None:
            return None
        if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
            raise ValueError(f"{field} 需为非空字符串数组")
        bad = sorted(set(values) - set(known))
        if bad:
            raise ValueError(f"{field} 含未知取值：" + "、".join(bad))
        return values

    species = check_list("species", known_species)
    forms = check_list("forms", known_forms)
    regions = check_list("regions", known_regions)
    return {
        "period_from": period_from,
        "period_to": period_to,
        "species": species,
        "forms": forms,
        "regions": regions,
        "known_species": known_species,
        "known_forms": known_forms,
        "known_regions": known_regions,
    }


def filter_transactions(transactions, boundary):
    selected = []
    for row in transactions:
        if boundary["period_from"] and row["day"] < boundary["period_from"]:
            continue
        if boundary["period_to"] and row["day"] > boundary["period_to"]:
            continue
        if boundary["species"] and row["species"] not in boundary["species"]:
            continue
        if boundary["forms"] and row["form"] not in boundary["forms"]:
            continue
        if boundary["regions"] and row["region"] not in boundary["regions"]:
            continue
        selected.append(row)
    return selected


def aggregate_entities(transactions):
    amount = defaultdict(Decimal)
    weight = defaultdict(Decimal)
    for row in transactions:
        amount[row["entity_id"]] += Decimal(row["amount"])
        weight[row["entity_id"]] += Decimal(str(row["weight_kg"]))
    return amount, weight


def coverage_report(catalog, selected_transactions, boundary):
    """对照 coverage 声明，明确分母口径与是否存在外部基准。"""
    months = sorted({row["day"][:7] for row in selected_transactions})
    regions = boundary["regions"] or sorted({row["region"] for row in selected_transactions})
    declarations = catalog.rows("coverage")
    by_key = {(row["period"], row["region"]): row for row in declarations}

    entries = []
    external_available = False
    for month in months:
        for region in regions:
            row = by_key.get((month, region))
            if row is None:
                entries.append({"period": month, "region": region, "status": "no_declaration",
                                "note": "该期间与地区没有覆盖声明。"})
                continue
            kind = row["coverage_kind"]
            entry = {"period": month, "region": region, "coverage_kind": kind,
                     "known_amount": row["known_amount"], "note": row["note"]}
            if kind == "registry":
                entry["status"] = "registry_only"
                if row["known_amount"] is not None:
                    if boundary["species"] or boundary["forms"]:
                        entry["observed_to_known_pct"] = None
                        entry["ratio_note"] = ("边界已按品类或形态收窄，而登记已知额覆盖全品类全形态，"
                                               "两者口径不可比，不计算比例。")
                    else:
                        observed = sum(
                            (Decimal(t["amount"]) for t in selected_transactions
                             if t["day"][:7] == month and t["region"] == region), Decimal())
                        entry["observed_registry_amount"] = money(observed)
                        entry["observed_to_known_pct"] = str(quantize(
                            observed / Decimal(row["known_amount"]) * HUNDRED))
                        entry["ratio_note"] = ("该比例是边界内观察登记额与登记已知额之比，不是市场覆盖率，"
                                               "可超过 100% 表示口径或期间不一致。")
            elif kind == "unknown":
                entry["status"] = "external_benchmark_missing"
            else:
                entry["status"] = "unverified_declaration"
                external_available = True
            entries.append(entry)
    return {
        "entries": entries,
        "external_benchmark_available": external_available,
        "denominator_basis": "所选边界内已登记成交合计；无外部基准时不得视为全市场分母。",
    }


# ---------------------------------------------------------------------------
# 份额与集中度
# ---------------------------------------------------------------------------


def _group_totals(groups, entity_amount, entity_weight):
    totals = []
    for group in groups:
        amount = sum((entity_amount.get(entity, Decimal()) for entity in group["members"]), Decimal())
        weight = sum((entity_weight.get(entity, Decimal()) for entity in group["members"]), Decimal())
        totals.append({"group_id": group["group_id"], "members": group["members"],
                       "amount": amount, "weight": weight})
    return totals


def concentration(groups, entity_amount, entity_weight):
    denominator_amount = sum(entity_amount.values(), Decimal())
    denominator_weight = sum(entity_weight.values(), Decimal())
    totals = _group_totals(groups, entity_amount, entity_weight)
    active = [item for item in totals if item["amount"] > 0 or item["weight"] > 0]

    def share(value, denominator):
        return value / denominator * HUNDRED if denominator else Decimal()

    ranking = []
    for item in sorted(active, key=lambda part: (-part["amount"], part["group_id"])):
        member_rows = []
        for entity in item["members"]:
            member_amount = entity_amount.get(entity, Decimal())
            member_weight = entity_weight.get(entity, Decimal())
            member_rows.append({
                "entity_id": entity,
                "amount": money(member_amount),
                "weight_kg": str(quantize(member_weight)),
                "contribution_pct_in_group": str(quantize(
                    member_amount / item["amount"] * HUNDRED)) if item["amount"] else None,
            })
        ranking.append({
            "group_id": item["group_id"],
            "amount": money(item["amount"]),
            "weight_kg": str(quantize(item["weight"])),
            "share_pct_amount": str(quantize(share(item["amount"], denominator_amount))),
            "share_pct_weight": str(quantize(share(item["weight"], denominator_weight))),
            "members": member_rows,
        })

    def metrics(denominator, field):
        if not denominator:
            return {"cr1_pct": None, "cr4_pct": None, "hhi_points": None, "active_groups": 0}
        exact = [share(item[field], denominator) for item in active]
        ordered = sorted(exact, reverse=True)
        hhi = sum((value * value for value in exact), Decimal())
        return {
            "cr1_pct": str(quantize(ordered[0])),
            "cr4_pct": str(quantize(sum(ordered[:4], Decimal()))),
            "hhi_points": str(quantize(hhi)),
            "active_groups": len(ordered),
        }

    return {
        "denominator": {
            "registered_amount": money(denominator_amount),
            "registered_weight_kg": str(quantize(denominator_weight)),
            "is_whole_market": False,
        },
        "by_amount": metrics(denominator_amount, "amount"),
        "by_weight": metrics(denominator_weight, "weight"),
        "ranking": ranking,
    }


# ---------------------------------------------------------------------------
# 情景区间与联合经营假设
# ---------------------------------------------------------------------------


def scenario_study(catalog, boundary_rows, entity_amount, entity_weight):
    """在四个显式假设下分别分组并计算集中度，给出区间与改变判断的边。"""
    scenarios = [
        {"include_unconfirmed": False, "joint_policy": "independent"},
        {"include_unconfirmed": True, "joint_policy": "independent"},
        {"include_unconfirmed": False, "joint_policy": "joint_group"},
        {"include_unconfirmed": True, "joint_policy": "joint_group"},
    ]
    results = []
    for scenario in scenarios:
        partition = build_partition(catalog, boundary_rows["as_of"], **scenario)
        metrics = concentration(partition["groups"], entity_amount, entity_weight)
        results.append({
            "scenario": scenario,
            "group_ids": [group["group_id"] for group in partition["groups"]],
            "group_count": len(partition["groups"]),
            "top_group": metrics["ranking"][0]["group_id"] if metrics["ranking"] else None,
            "by_amount": metrics["by_amount"],
            "by_weight": metrics["by_weight"],
        })

    def value_range(field, metric_field):
        values = [entry[field][metric_field] for entry in results]
        if any(value is None for value in values):
            return {"min": None, "max": None}
        parsed = sorted((Decimal(value), index) for index, value in enumerate(values))
        low, high = parsed[0], parsed[-1]
        return {
            "min": {"value": str(low[0]), "scenario": results[low[1]]["scenario"]},
            "max": {"value": str(high[0]), "scenario": results[high[1]]["scenario"]},
        }

    baseline = results[0]
    baseline_partition = build_partition(catalog, boundary_rows["as_of"])
    decision_changing = []
    for entry in results[1:]:
        partition = build_partition(catalog, boundary_rows["as_of"], **entry["scenario"])
        base_voting = set(baseline_partition["effective_edges"]["voting"])
        new_voting = sorted(set(partition["effective_edges"]["voting"]) - base_voting)
        new_joint = partition["effective_edges"]["joint_used"]
        baseline_hhi = baseline["by_amount"]["hhi_points"]
        entry_hhi = entry["by_amount"]["hhi_points"]
        hhi_delta = None if baseline_hhi is None else str(quantize(
            Decimal(entry_hhi) - Decimal(baseline_hhi)))
        decision_changing.append({
            "scenario": entry["scenario"],
            "group_count": entry["group_count"],
            "top_group_changes": entry["top_group"] != baseline["top_group"],
            "hhi_amount_delta_points": hhi_delta,
            "newly_active_edge_ids": sorted(new_voting + new_joint),
            "reason": _scenario_reason(entry["scenario"], bool(new_voting), bool(new_joint)),
        })

    return {
        "scenario_results": results,
        "range": {
            "hhi_amount_points": value_range("by_amount", "hhi_points"),
            "cr1_amount_pct": value_range("by_amount", "cr1_pct"),
            "cr4_amount_pct": value_range("by_amount", "cr4_pct"),
            "hhi_weight_points": value_range("by_weight", "hhi_points"),
            "cr1_weight_pct": value_range("by_weight", "cr1_pct"),
            "cr4_weight_pct": value_range("by_weight", "cr4_pct"),
        },
        "decision_changing_edges": decision_changing,
        "note": "区间只反映显式列名假设下的统计变化，不代表任何确定性结论。",
    }


def _scenario_reason(scenario, added_voting, added_joint):
    parts = []
    if scenario["include_unconfirmed"] and added_voting:
        parts.append("纳入未确认表决权边")
    if scenario["joint_policy"] == "joint_group" and added_joint:
        parts.append("按共同控制协议合并")
    return "、".join(parts) if parts else "分组与基线相同，仅参数组合不同"


def joint_operation_study(catalog, partition, entity_amount, entity_weight, participants):
    if not isinstance(participants, list) or not participants or not all(
            isinstance(item, str) for item in participants):
        raise ValueError("joint_operation 需为非空实体 ID 数组")
    known = {row["id"] for row in catalog.rows("entities")}
    unknown = sorted(set(participants) - known)
    if unknown:
        raise ValueError("joint_operation 含未知实体：" + "、".join(unknown))

    lookup = _group_lookup(partition["groups"])
    involved_groups = sorted({lookup[entity] for entity in participants})
    if len(involved_groups) < 2:
        raise ValueError("联合经营假设至少涉及基线分组下两个不同经营主体")

    before = concentration(partition["groups"], entity_amount, entity_weight)
    merged_groups = []
    merged_ids = set()
    for group in partition["groups"]:
        if group["group_id"] in involved_groups:
            merged_ids.update(group["members"])
            merged_groups.append(group)
    merged = {
        "group_id": "JOINT",
        "members": sorted(merged_ids),
        "voting_roots": [],
        "joint_agreement_ids": [],
        "member_evidence": [evidence for group in merged_groups
                            for evidence in group["member_evidence"]],
    }
    after_groups = [group for group in partition["groups"]
                    if group["group_id"] not in involved_groups] + [merged]
    after = concentration(after_groups, entity_amount, entity_weight)

    def delta(field):
        def subtract(key):
            if after[field][key] is None:
                return None
            return str(quantize(Decimal(after[field][key]) - Decimal(before[field][key])))

        return {key: subtract(key) for key in ("cr1_pct", "cr4_pct", "hhi_points")}

    merged_row = next(row for row in after["ranking"] if row["group_id"] == "JOINT")
    return {
        "participating_entities": sorted(participants),
        "participating_baseline_groups": involved_groups,
        "merged_member_entity_ids": sorted(merged_ids),
        "merged_group": merged_row,
        "before": {"by_amount": before["by_amount"], "by_weight": before["by_weight"],
                   "ranking": before["ranking"]},
        "after": {"by_amount": after["by_amount"], "by_weight": after["by_weight"],
                  "ranking": after["ranking"]},
        "delta": {"by_amount": delta("by_amount"), "by_weight": delta("by_weight")},
        "note": "联合经营为显式假设的试算情景，合并结果可按 members 拆回原登记主体，不自动给出合法性结论。",
    }


# ---------------------------------------------------------------------------
# 对外组装
# ---------------------------------------------------------------------------


def control_report(catalog, as_of=None, include_unconfirmed=False, joint_policy="independent"):
    return control_view(catalog, as_of, include_unconfirmed, joint_policy)


def concentration_report(catalog, raw_boundary=None, raw_scenario=None, joint_operation=None):
    raw_scenario = raw_scenario or {}
    allowed = {"as_of", "include_unconfirmed", "joint_policy"}
    unknown = set(raw_scenario) - allowed
    if unknown:
        raise ValueError("scenario 包含未知字段：" + "、".join(sorted(unknown)))
    if "include_unconfirmed" in raw_scenario and not isinstance(
            raw_scenario["include_unconfirmed"], bool):
        raise ValueError("include_unconfirmed 需为布尔值")
    if "joint_policy" in raw_scenario and raw_scenario["joint_policy"] not in JOINT_POLICIES:
        raise ValueError("joint_policy 仅支持 independent 或 joint_group")
    if "as_of" in raw_scenario:
        as_date(raw_scenario["as_of"])
    boundary = parse_boundary(raw_boundary or {}, catalog)
    selected = filter_transactions(catalog.rows("transactions"), boundary)
    entity_amount, entity_weight = aggregate_entities(selected)
    partition = build_partition(
        catalog,
        raw_scenario.get("as_of") or date.today().isoformat(),
        bool(raw_scenario.get("include_unconfirmed", False)),
        raw_scenario.get("joint_policy", "independent"),
    )
    baseline = concentration(partition["groups"], entity_amount, entity_weight)
    study = scenario_study(
        catalog,
        {"as_of": partition["as_of"]},
        entity_amount,
        entity_weight,
    )
    report = {
        "source_fingerprint": catalog.fingerprint,
        "boundary": {key: value for key, value in boundary.items()
                     if key.startswith("period_") or key in ("species", "forms", "regions")},
        "transaction_count": len(selected),
        "coverage": coverage_report(catalog, selected, boundary),
        "baseline_scenario": partition["scenario"],
        "groups": partition["groups"],
        "ambiguous_edges": edge_effects(partition, catalog.rows("ownership")),
        "cross_holdings": partition["cross_holdings"],
        "baseline_concentration": baseline,
        "scenario_range": study,
        "caveats": list(CAVEATS),
    }
    if joint_operation is not None:
        report["joint_operation"] = joint_operation_study(
            catalog, partition, entity_amount, entity_weight, joint_operation)
    return report
