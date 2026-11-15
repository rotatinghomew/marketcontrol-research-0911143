import unittest
from decimal import Decimal

from marketcontrol.catalog import Catalog
from marketcontrol.concentration import (
    build_partition,
    concentration,
    concentration_report,
    control_report,
    edge_effects,
    filter_transactions,
    parse_boundary,
)


class ControlPartitionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog("data")

    def test_indirect_voting_chain_is_one_group_with_evidence_path(self):
        partition = build_partition(self.catalog, "2026-09-15")
        group = next(group for group in partition["groups"] if "E7" in group["members"])
        self.assertEqual(group["members"], ["E0", "E1", "E12", "E17", "E7"])
        evidence = {item["entity_id"]: item for item in group["member_evidence"]}
        self.assertEqual(evidence["E7"]["control_path_edge_ids"], ["O11", "O10"])
        self.assertEqual(evidence["E0"]["control_path_edge_ids"], ["O0"])

    def test_equity_edges_never_connect_groups(self):
        partition = build_partition(self.catalog, "2026-09-15")
        lookup = {entity: group["group_id"] for group in partition["groups"] for entity in group["members"]}
        # O3 是 E13 对 E3 的 20% 经济权益，E2 同受 E13 控制，E3 必须保持独立
        self.assertNotEqual(lookup["E2"], lookup["E3"])
        self.assertIn("O3", partition["effective_edges"]["equity_not_control"])

    def test_cross_holdings_are_flagged_but_not_merged(self):
        partition = build_partition(self.catalog, "2026-09-15")
        self.assertEqual(partition["cross_holdings"][0]["edge_ids"], ["O6", "O7"])
        lookup = {entity: group["group_id"] for group in partition["groups"] for entity in group["members"]}
        self.assertNotEqual(lookup["E14"], lookup["E15"])

    def test_joint_agreement_is_independent_by_default_and_merged_when_assumed(self):
        independent = build_partition(self.catalog, "2026-09-15", joint_policy="independent")
        lookup = {entity: group["group_id"] for group in independent["groups"] for entity in group["members"]}
        self.assertNotEqual(lookup["E14"], lookup["E4"])
        self.assertIn("O4", independent["effective_edges"]["joint_held_independent"])

        merged = build_partition(self.catalog, "2026-09-15", joint_policy="joint_group")
        merged_lookup = {entity: group["group_id"] for group in merged["groups"] for entity in group["members"]}
        self.assertEqual(merged_lookup["E14"], merged_lookup["E15"])
        self.assertEqual(merged_lookup["E14"], merged_lookup["E4"])
        self.assertIn("J1", next(
            group for group in merged["groups"] if "E4" in group["members"])["joint_agreement_ids"])

    def test_unconfirmed_edges_excluded_by_default_and_included_under_assumption(self):
        baseline = build_partition(self.catalog, "2026-09-15")
        lookup = {entity: group["group_id"] for group in baseline["groups"] for entity in group["members"]}
        self.assertNotEqual(lookup["E16"], lookup["E5"])
        excluded = {edge["edge_id"]: edge for edge in edge_effects(baseline, self.catalog.rows("ownership"))}
        self.assertTrue(excluded["O8"]["would_merge_groups"])

        assumed = build_partition(self.catalog, "2026-09-15", include_unconfirmed=True)
        assumed_lookup = {entity: group["group_id"] for group in assumed["groups"]
                          for entity in group["members"]}
        self.assertEqual(assumed_lookup["E16"], assumed_lookup["E5"])
        self.assertEqual(assumed_lookup["E16"], assumed_lookup["E6"])

    def test_validity_window_is_half_open(self):
        # O1 在 2026-10-01 终止：9 月底有效，10 月当天起失效
        september = build_partition(self.catalog, "2026-09-30")
        self.assertIn("O1", september["effective_edges"]["voting"])
        october = build_partition(self.catalog, "2026-10-01")
        self.assertNotIn("O1", october["effective_edges"]["voting"])
        expired = next(edge for edge in october["excluded_edges"] if edge["id"] == "O1")
        self.assertEqual(expired["exclusion_reason"], "expired")

    def test_every_entity_is_partitioned_exactly_once(self):
        partition = build_partition(self.catalog, "2026-09-15")
        all_members = [entity for group in partition["groups"] for entity in group["members"]]
        self.assertEqual(sorted(all_members), sorted(row["id"] for row in self.catalog.rows("entities")))


class BoundaryAndCoverageTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog("data")

    def test_period_shorthand_expands_to_month_bounds(self):
        boundary = parse_boundary({"period": "2026-09"}, self.catalog)
        self.assertEqual((boundary["period_from"], boundary["period_to"]),
                         ("2026-09-01", "2026-09-30"))
        rows = filter_transactions(self.catalog.rows("transactions"), boundary)
        self.assertTrue(all(row["day"].startswith("2026-09") for row in rows))
        self.assertEqual(len(rows), 300)

    def test_form_boundary_separates_live_and_frozen_markets(self):
        live = parse_boundary({"forms": ["活鲜"]}, self.catalog)
        frozen = parse_boundary({"forms": ["冻品"]}, self.catalog)
        live_rows = filter_transactions(self.catalog.rows("transactions"), live)
        frozen_rows = filter_transactions(self.catalog.rows("transactions"), frozen)
        self.assertTrue(all(row["form"] == "活鲜" for row in live_rows))
        self.assertTrue(all(row["form"] == "冻品" for row in frozen_rows))
        self.assertEqual(len(live_rows) + len(frozen_rows), len(self.catalog.rows("transactions")))

    def test_unknown_boundary_value_rejected(self):
        with self.assertRaises(ValueError):
            parse_boundary({"species": ["不存在"]}, self.catalog)
        with self.assertRaises(ValueError):
            parse_boundary({"period": "2026-09", "period_from": "2026-09-01"}, self.catalog)

    def test_coverage_marks_missing_external_benchmark(self):
        report = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09", "regions": ["片区2"]},
            raw_scenario={"as_of": "2026-09-15"},
        )
        entry = report["coverage"]["entries"][0]
        self.assertEqual(entry["status"], "external_benchmark_missing")
        self.assertFalse(report["coverage"]["external_benchmark_available"])
        self.assertFalse(report["baseline_concentration"]["denominator"]["is_whole_market"])

    def test_coverage_ratio_skipped_when_species_or_form_narrows_boundary(self):
        narrowed = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09", "regions": ["片区0"], "forms": ["活鲜"]},
            raw_scenario={"as_of": "2026-09-15"},
        )
        entry = narrowed["coverage"]["entries"][0]
        self.assertIsNone(entry["observed_to_known_pct"])
        full = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09", "regions": ["片区0"]},
            raw_scenario={"as_of": "2026-09-15"},
        )
        self.assertIsNotNone(full["coverage"]["entries"][0]["observed_to_known_pct"])


class ConcentrationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog("data")

    def test_shares_use_registered_denominator_and_sum_to_one_hundred(self):
        report = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09"},
            raw_scenario={"as_of": "2026-09-15"},
        )
        ranking = report["baseline_concentration"]["ranking"]
        shares = sum(Decimal(row["share_pct_amount"]) for row in ranking)
        self.assertLess(abs(shares - Decimal("100")), Decimal("0.1"))
        observed = sum(Decimal(row["amount"]) for row in self.catalog.rows("transactions")
                       if row["day"].startswith("2026-09"))
        self.assertEqual(Decimal(report["baseline_concentration"]["denominator"]["registered_amount"]), observed)

    def test_scenario_range_is_bounded_by_named_assumptions(self):
        report = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09"},
            raw_scenario={"as_of": "2026-09-15"},
        )
        hhi = report["scenario_range"]["range"]["hhi_amount_points"]
        self.assertLess(Decimal(hhi["min"]["value"]), Decimal(hhi["max"]["value"]))
        self.assertEqual(hhi["min"]["scenario"]["include_unconfirmed"], False)
        self.assertEqual(hhi["max"]["scenario"]["include_unconfirmed"], True)
        reasons = {tuple(sorted(item["scenario"].items())): item
                   for item in report["scenario_range"]["decision_changing_edges"]}
        flagged = next(item for item in report["scenario_range"]["decision_changing_edges"]
                       if item["scenario"]["include_unconfirmed"])
        self.assertIn("O8", flagged["newly_active_edge_ids"])
        self.assertIn("O9", flagged["newly_active_edge_ids"])

    def test_amount_and_weight_can_rank_differently(self):
        report = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09"},
            raw_scenario={"as_of": "2026-09-15"},
        )
        metrics = report["baseline_concentration"]
        self.assertIsNotNone(metrics["by_weight"]["hhi_points"])
        self.assertNotEqual(metrics["by_amount"]["hhi_points"], metrics["by_weight"]["hhi_points"])

    def test_joint_operation_is_decomposable_and_changes_hhi(self):
        report = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09"},
            raw_scenario={"as_of": "2026-09-15"},
            joint_operation=["E8", "E10"],
        )
        operation = report["joint_operation"]
        self.assertEqual(operation["merged_member_entity_ids"], ["E10", "E8"])
        self.assertEqual(len(operation["participating_baseline_groups"]), 2)
        self.assertGreater(Decimal(operation["delta"]["by_amount"]["hhi_points"]), Decimal("0"))
        # 合并后的份额等于原两个主体份额之和，可拆回原主体
        before = {row["group_id"]: row for row in operation["before"]["ranking"]}
        original_amount = sum(
            (Decimal(member["amount"]) for group_id in operation["participating_baseline_groups"]
             for member in before[group_id]["members"]), Decimal())
        self.assertEqual(Decimal(operation["merged_group"]["amount"]), original_amount)

    def test_joint_operation_rejects_same_group_and_unknown_entity(self):
        with self.assertRaises(ValueError):
            concentration_report(
                self.catalog,
                raw_boundary={"period": "2026-09"},
                raw_scenario={"as_of": "2026-09-15"},
                joint_operation=["E0", "E1"],  # 基线已在同一经营主体
            )
        with self.assertRaises(ValueError):
            concentration_report(
                self.catalog,
                raw_boundary={"period": "2026-09"},
                raw_scenario={"as_of": "2026-09-15"},
                joint_operation=["E0", "E99"],
            )

    def test_report_carries_caveats_but_no_legal_verdict(self):
        report = concentration_report(
            self.catalog,
            raw_boundary={"period": "2026-09"},
            raw_scenario={"as_of": "2026-09-15"},
        )
        self.assertTrue(report["caveats"])
        serialized = str(report)
        # 可以声明"不构成结论"，但不能出现认定性标签
        for forbidden in ("违法成立", "认定违法", "构成垄断", "处罚", "裁定"):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("不构成合法或违法结论", serialized)

    def test_empty_boundary_returns_null_metrics_not_crash(self):
        report = concentration_report(
            self.catalog,
            raw_boundary={"period_from": "2030-01-01", "period_to": "2030-01-31"},
            raw_scenario={"as_of": "2026-09-15"},
        )
        self.assertEqual(report["transaction_count"], 0)
        self.assertIsNone(report["baseline_concentration"]["by_amount"]["hhi_points"])


class FakeCatalog:
    def __init__(self, tables, fingerprint="fake"):
        self.tables = tables
        self.fingerprint = fingerprint

    def rows(self, name):
        return self.tables[name]


class ConcentrationArithmeticTests(unittest.TestCase):
    def test_hhi_and_cr4_on_hand_built_groups(self):
        groups = [
            {"group_id": "G01", "members": ["A"], "voting_roots": ["A"],
             "joint_agreement_ids": [], "member_evidence": []},
            {"group_id": "G02", "members": ["B", "C"], "voting_roots": ["B"],
             "joint_agreement_ids": [], "member_evidence": []},
        ]
        amount = {"A": Decimal("60"), "B": Decimal("30"), "C": Decimal("10")}
        weight = {"A": Decimal("5"), "B": Decimal("3"), "C": Decimal("2")}
        result = concentration(groups, amount, weight)
        self.assertEqual(result["by_amount"]["cr1_pct"], "60.00")
        self.assertEqual(result["by_amount"]["cr4_pct"], "100.00")
        # 0.6^2 + 0.4^2 = 0.52 -> HHI 点数 5200
        self.assertEqual(result["by_amount"]["hhi_points"], "5200.00")


if __name__ == "__main__":
    unittest.main()
