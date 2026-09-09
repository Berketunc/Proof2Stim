import unittest

from proof2stim.replay import ApbCsbLegalityChecker
from proof2stim.targets import CycleSample


def cycle(**overrides: int) -> CycleSample:
    values = {
        "psel": 0,
        "penable": 0,
        "pwrite": 0,
        "csb2nvdla_valid": 0,
        "csb2nvdla_ready": 0,
        "nvdla2csb_valid": 0,
        "nvdla2csb_data": 0,
        "pready": 1,
        "prdata": 0,
        "paddr": 0,
        "pwdata": 0,
    }
    values.update(overrides)
    return CycleSample(**values)


class ReplayLegalityTests(unittest.TestCase):
    def test_legal_delayed_read(self) -> None:
        checker = ApbCsbLegalityChecker()
        checker.observe(cycle(psel=1))
        checker.observe(cycle(psel=1, penable=1, csb2nvdla_valid=1, pready=0, paddr=0x100))
        checker.observe(
            cycle(
                psel=1,
                penable=1,
                csb2nvdla_valid=1,
                csb2nvdla_ready=1,
                pready=0,
                paddr=0x100,
            )
        )
        checker.observe(cycle(psel=1, penable=1, pready=0, paddr=0x100))
        checker.observe(
            cycle(
                psel=1,
                penable=1,
                nvdla2csb_valid=1,
                nvdla2csb_data=0x55,
                pready=1,
                prdata=0x55,
                paddr=0x100,
            )
        )
        self.assertTrue(checker.legal, checker.errors)
        self.assertEqual(checker.accepted_reads, 1)
        self.assertEqual(checker.responses, 1)

    def test_rejects_access_without_setup(self) -> None:
        checker = ApbCsbLegalityChecker()
        checker.observe(cycle(psel=1, penable=1, pready=0))
        self.assertFalse(checker.legal)
        self.assertIn("APB access lacked setup or waiting predecessor", checker.errors)


if __name__ == "__main__":
    unittest.main()
