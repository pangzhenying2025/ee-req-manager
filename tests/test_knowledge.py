import unittest

from automotive_knowledge import (
    REQUIREMENT_TEMPLATES,
    STANDARDS_CATALOG,
    TRACEABILITY_BLUEPRINTS,
    assess_requirement_quality,
)


class RequirementQualityTests(unittest.TestCase):
    def test_complete_functional_requirement_passes_review_gate(self):
        result = assess_requirement_quality(
            "在车辆处于驻车状态时，BCM 应在收到有效闭锁请求后 200 ms 内锁止全部车门。",
            source="VEH-REQ-001",
            rationale="防止车辆未闭锁",
            verification_method="Test",
            acceptance_criteria="给定四门关闭，发送闭锁请求后 200 ms 内四门锁状态均为 Locked。",
            req_type="Functional",
        )
        self.assertTrue(result["ready_for_review"])
        self.assertGreaterEqual(result["score"], 75)

    def test_vague_untraceable_requirement_is_rejected(self):
        result = assess_requirement_quality("系统应尽快正常响应。")
        codes = {item["code"] for item in result["findings"]}
        self.assertFalse(result["ready_for_review"])
        self.assertTrue({"VAGUE", "SOURCE", "VERIFY", "ACCEPTANCE"}.issubset(codes))
        self.assertNotIn("ATOMIC", codes)

    def test_response_word_does_not_count_as_an_obligation(self):
        result = assess_requirement_quality(
            "系统快速响应。",
            source="STAKE-01",
            verification_method="Test",
            acceptance_criteria="记录响应时间。",
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("OBLIGATION", codes)

    def test_safety_requirement_requires_asil_and_safe_reaction(self):
        result = assess_requirement_quality(
            "制动控制器应在 10 ms 内记录异常。",
            source="SG-01",
            rationale="安全目标分解",
            verification_method="Test",
            acceptance_criteria="注入异常后 10 ms 内生成事件记录。",
            req_type="Safety",
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("ASIL", codes)
        self.assertIn("SAFE_STATE", codes)

    def test_curated_catalog_has_traceable_sources(self):
        self.assertGreaterEqual(len(STANDARDS_CATALOG), 4)
        self.assertTrue(all(item["url"].startswith("https://") for item in STANDARDS_CATALOG))
        self.assertIn("Safety", REQUIREMENT_TEMPLATES)
        self.assertGreaterEqual(len(TRACEABILITY_BLUEPRINTS), 3)


if __name__ == "__main__":
    unittest.main()
