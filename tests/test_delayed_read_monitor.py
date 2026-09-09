import unittest

from proof2stim.targets import CycleSample, DelayedReadMonitor


def cycle(**overrides: int) -> CycleSample:
    values = {
        "psel": 1,
        "penable": 1,
        "pwrite": 0,
        "csb2nvdla_valid": 0,
        "csb2nvdla_ready": 0,
        "nvdla2csb_valid": 0,
        "nvdla2csb_data": 0,
        "pready": 0,
        "prdata": 0,
    }
    values.update(overrides)
    return CycleSample(**values)


class DelayedReadMonitorTests(unittest.TestCase):
    def test_legal_delayed_read_hits_target(self) -> None:
        monitor = DelayedReadMonitor()
        monitor.observe(cycle(csb2nvdla_valid=1))
        monitor.observe(cycle(csb2nvdla_valid=1, csb2nvdla_ready=1))
        monitor.observe(cycle())
        monitor.observe(
            cycle(
                nvdla2csb_valid=1,
                nvdla2csb_data=0xCAFE_BABE,
                pready=1,
                prdata=0xCAFE_BABE,
            )
        )
        self.assertTrue(monitor.hit)
        self.assertEqual(monitor.accepted_requests, 1)
        self.assertIsNone(monitor.protocol_error)

    def test_duplicate_request_is_rejected(self) -> None:
        monitor = DelayedReadMonitor()
        monitor.observe(cycle(csb2nvdla_valid=1))
        monitor.observe(cycle(csb2nvdla_valid=1, csb2nvdla_ready=1))
        monitor.observe(cycle(csb2nvdla_valid=1, csb2nvdla_ready=1))
        monitor.observe(cycle())
        monitor.observe(
            cycle(
                nvdla2csb_valid=1,
                nvdla2csb_data=0x1234,
                pready=1,
                prdata=0x1234,
            )
        )
        self.assertFalse(monitor.hit)
        self.assertTrue(monitor.duplicate_request)

    def test_mismatched_return_data_does_not_hit(self) -> None:
        monitor = DelayedReadMonitor()
        monitor.observe(cycle(csb2nvdla_valid=1))
        monitor.observe(cycle(csb2nvdla_valid=1, csb2nvdla_ready=1))
        monitor.observe(cycle())
        monitor.observe(
            cycle(
                nvdla2csb_valid=1,
                nvdla2csb_data=0xCAFE_BABE,
                pready=1,
                prdata=0xDEAD_BEEF,
            )
        )
        self.assertFalse(monitor.hit)


if __name__ == "__main__":
    unittest.main()
