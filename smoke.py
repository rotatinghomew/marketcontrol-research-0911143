import json
import tempfile
import threading
from urllib.request import Request, urlopen

from marketcontrol.service import Application, make_server


def main():
    with tempfile.TemporaryDirectory() as state:
        server = make_server(Application("data", state), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            for path in ("/health", "/tables", "/view"):
                with urlopen(base + path, timeout=5) as response:
                    print(path, json.dumps(json.load(response), ensure_ascii=False))
            request = Request(base + "/cases", data=json.dumps({"label": "月度经营讨论", "options": {"period": "2026-09"}}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                created = json.load(response)
            with urlopen(base + "/cases/" + created["id"], timeout=5) as response:
                restored = json.load(response)
            assert created == restored
            print("研究记录已回读", restored["id"], restored["source_fingerprint"])

            control_body = json.dumps({"as_of": "2026-09-15"}).encode()
            control_request = Request(base + "/research/control", data=control_body,
                                      headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(control_request, timeout=5) as response:
                control = json.load(response)
            print("控制分组", control["control"]["scenario"],
                  len(control["control"]["groups"]), "个经营主体",
                  len(control["control"]["ambiguous_edges"]), "条待判定边")

            concentration_body = json.dumps({
                "boundary": {"period": "2026-09", "forms": ["冻品"]},
                "scenario": {"as_of": "2026-09-15"},
                "joint_operation": ["E8", "E10"],
            }, ensure_ascii=False).encode()
            concentration_request = Request(
                base + "/research/concentration", data=concentration_body,
                headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(concentration_request, timeout=5) as response:
                research = json.load(response)["report"]
            print("集中度", research["baseline_concentration"]["by_amount"],
                  "HHI区间", research["scenario_range"]["range"]["hhi_amount_points"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
