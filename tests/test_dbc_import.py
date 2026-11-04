import unittest
from types import SimpleNamespace

from services.dbc_import import parse_dbc_file


class DbcImportTests(unittest.TestCase):
    def test_parser_preserves_physical_scaling_and_byte_order(self):
        content = b'''VERSION ""
NS_ :
BS_:
BU_: BCM ICM GW
BO_ 769 Door: 8 BCM
 SG_ IntelSpeed : 0|16@1+ (0.1,-10) [-10|250] "km/h" ICM,GW
 SG_ MotorolaStatus : 23|8@0+ (1,0) [0|255] "" ICM
'''
        signals, database = parse_dbc_file(SimpleNamespace(getvalue=lambda: content))
        self.assertEqual(signals[0]["byte_order"], "Intel")
        self.assertEqual(signals[0]["factor"], 0.1)
        self.assertEqual(signals[0]["offset"], -10)
        self.assertEqual(signals[1]["byte_order"], "Motorola")
        self.assertEqual(database.messages[0].signals[0].receivers, ["ICM", "GW"])
