import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from marketcontrol.service import Application, make_server


class ResearchEndpointTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.application = Application("data", Path(self.workspace.name) / "state")

    def post(self, path, payload):
        return self.application.dispatch("POST", path, payload)

    def test_control_endpoint_baseline_grouping(self):
        status, result = self.post("/research/control", {"as_of": "2026-09-15"})
        self.assertEqual(status, 200)
        control = result["control"]
        self.assertEqual(control["scenario"], {
            "include_unconfirmed": False, "joint_policy": "independent"})
        self.assertTrue(all(len(group["members"]) >= 1 for group in control["groups"]))
        self.assertIn("ambiguous_edges", control)

    def test_control_endpoint_validates_arguments(self):
        self.assertEqual(self.post("/research/control", {"as_of": "09-15"})[0], 400)
        self.assertEqual(self.post("/research/control", {"joint_policy": "shared"})[0], 400)
        self.assertEqual(self.post("/research/control", {"extra": 1})[0], 400)
        self.assertEqual(self.post("/research/control", "not-an-object")[0], 400)

    def test_concentration_endpoint_full_workflow(self):
        payload = {
            "boundary": {"period": "2026-09", "forms": ["冻品"]},
            "scenario": {"as_of": "2026-09-15"},
            "joint_operation": ["E8", "E10"],
        }
        status, result = self.post("/research/concentration", payload)
        self.assertEqual(status, 200)
        report = result["report"]
        self.assertTrue(report["coverage"]["entries"])
        self.assertFalse(report["coverage"]["external_benchmark_available"])
        self.assertIn("scenario_range", report)
        self.assertEqual(report["joint_operation"]["merged_member_entity_ids"], ["E10", "E8"])
        self.assertTrue(report["caveats"])

    def test_concentration_endpoint_rejects_unknown_fields(self):
        self.assertEqual(self.post("/research/concentration", {"boundary": {}, "surprise": 1})[0], 400)
        bad_boundary = {"boundary": {"regions": ["不存在片区"]}}
        self.assertEqual(self.post("/research/concentration", bad_boundary)[0], 400)

    def test_research_endpoints_are_read_only_over_http(self):
        server = make_server(self.application, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        body = json.dumps({"as_of": "2026-09-15"}).encode()
        request = Request(base + "/research/control", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
            payload = json.load(response)
        self.assertEqual(payload["source_fingerprint"], self.application.catalog.fingerprint)


if __name__ == "__main__":
    unittest.main()
