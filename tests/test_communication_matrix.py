import tempfile
import unittest
from pathlib import Path

from communication_matrix import compare_matrices, load_matrix

DBC_BASE = '''VERSION ""
NS_ :
BS_:
BU_: VCU ICM
BO_ 256 VCU_Status: 8 VCU
 SG_ VehicleSpeed : 0|16@1+ (0.1,0) [0|250] "km/h" ICM
'''

DBC_CHANGED = '''VERSION ""
NS_ :
BS_:
BU_: VCU ICM ADAS
BO_ 256 VCU_Status: 8 VCU
 SG_ VehicleSpeed : 0|16@1+ (0.01,0) [0|300] "km/h" ICM,ADAS
 SG_ DriveReady : 16|1@1+ (1,0) [0|1] "" ICM
'''


class CommunicationMatrixTests(unittest.TestCase):
    def _write(self, folder: str, name: str, content: str) -> Path:
        path = Path(folder) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_dbc_is_normalized_with_engineering_attributes(self):
        with tempfile.TemporaryDirectory() as folder:
            signals = load_matrix(self._write(folder, "base.dbc", DBC_BASE))
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.frame_id, 0x100)
        self.assertEqual(signal.byte_order, "Intel")
        self.assertEqual(signal.factor, 0.1)
        self.assertEqual(signal.receivers, ("ICM",))

    def test_compare_reports_add_and_field_level_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            baseline = load_matrix(self._write(folder, "base.dbc", DBC_BASE))
            candidate = load_matrix(self._write(folder, "candidate.dbc", DBC_CHANGED))
        summary, rows = compare_matrices(baseline, candidate)
        self.assertEqual(summary["新增信号"], 1)
        self.assertEqual(summary["修改信号"], 1)
        self.assertEqual(summary["删除信号"], 0)
        changed_fields = {row["属性"] for row in rows if row["信号"] == "VehicleSpeed"}
        self.assertTrue({"精度 Factor", "最大值", "接收节点"}.issubset(changed_fields))

    def test_signal_removed_is_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            baseline = load_matrix(self._write(folder, "base.dbc", DBC_CHANGED))
            candidate = load_matrix(self._write(folder, "candidate.dbc", DBC_BASE))
        summary, _ = compare_matrices(baseline, candidate)
        self.assertEqual(summary["删除信号"], 1)


if __name__ == "__main__":
    unittest.main()
