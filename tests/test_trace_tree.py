import unittest
from types import SimpleNamespace

from requirements_ui import _build_function_requirement_trace, _legacy_requirement_type


def item(**values):
    return SimpleNamespace(**values)


class FunctionRequirementTraceTests(unittest.TestCase):
    def test_level_and_nature_map_to_legacy_type(self):
        self.assertEqual(_legacy_requirement_type("Subsystem", "Functional"), "Functional")
        self.assertEqual(_legacy_requirement_type("Function", "Functional"), "Functional")
        self.assertEqual(_legacy_requirement_type("System", "Functional"), "System")
        self.assertEqual(_legacy_requirement_type("System", "Safety"), "Safety")
        self.assertEqual(_legacy_requirement_type("Interface", "Interface"), "Interface")

    def test_lc_atomic_requirements_signals_and_verification_are_grouped(self):
        subsystem = item(id=1, func_id="SL01", name="高压控制", module="VCU", category="动力域")
        logical = item(id=2, func_id="LC01-01", name="高压上下电", module="VCU", category="动力域")
        atomic = item(id=3, func_id="AF-008", name="高压上电时序", module="VCU", category="动力域")
        relations = [
            item(source_id=1, target_id=2, rel_type="分解"),
            item(source_id=2, target_id=3, rel_type="分解"),
            item(source_id=1, target_id=3, rel_type="数据流"),
        ]

        logical_req = item(id=10, req_id="SYS-LC01-01", title="高压上下电", req_type="System", parent_id=None)
        system_req = item(id=11, req_id="SYS-AF-008", title="高压上电时序", req_type="System", parent_id=10)
        interface_req = item(id=12, req_id="IF-001", title="上电请求信号", req_type="Interface", parent_id=11)
        verification_req = item(id=13, req_id="VER-AF-008", title="高压上电验证", req_type="Verification", parent_id=11)
        signal = item(id=20, signal_id="VCU_BMS_WorkReq", name="VCU_BMS_WorkReq")
        links = [
            item(source_type="Requirement", source_id=10, target_type="Function", target_id=2, link_type="allocates"),
            item(source_type="Requirement", source_id=11, target_type="Function", target_id=3, link_type="allocates"),
            item(source_type="Requirement", source_id=12, target_type="Signal", target_id=20, link_type="allocates"),
            item(source_type="Requirement", source_id=13, target_type="Requirement", target_id=11, link_type="verifies"),
        ]

        tree = _build_function_requirement_trace(
            [subsystem, logical, atomic],
            relations,
            [logical_req, system_req, interface_req, verification_req],
            [signal],
            links,
        )

        atomic_node = tree["subsystems"][0]["logicals"][0]["atomics"][0]
        self.assertEqual([row["id"] for row in atomic_node["requirements"]], ["SYS-AF-008"])
        self.assertEqual([row["id"] for row in atomic_node["interfaces"]], ["IF-001"])
        self.assertEqual([row["id"] for row in atomic_node["signals"]], ["VCU_BMS_WorkReq"])
        self.assertEqual([row["id"] for row in atomic_node["verifications"]], ["VER-AF-008"])
        self.assertEqual(tree["summary"]["requirements_covered"], 1)
        self.assertEqual(tree["summary"]["signals_covered"], 1)
        self.assertEqual(tree["summary"]["verification_covered"], 1)


if __name__ == "__main__":
    unittest.main()
