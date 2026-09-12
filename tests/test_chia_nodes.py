import importlib.util
import unittest

CHIA_AVAILABLE = importlib.util.find_spec("chia") is not None


@unittest.skipUnless(CHIA_AVAILABLE, "CHIA optional dependency is not installed")
class ChiaNodeTests(unittest.TestCase):
    def test_profiled_dependency_is_unwrapped(self):
        from chia.trace.profiler import _ProfiledResult

        from proof2stim.chia_nodes.stages import _unwrap_dependencies

        value = {"id": "formal", "status": "passed"}
        wrapped = _ProfiledResult(
            value=value,
            worker_ip="127.0.0.1",
            worker_id="worker",
            node_id="node",
            exec_time_s=0.1,
        )

        self.assertEqual((value,), _unwrap_dependencies((wrapped,)))


if __name__ == "__main__":
    unittest.main()
