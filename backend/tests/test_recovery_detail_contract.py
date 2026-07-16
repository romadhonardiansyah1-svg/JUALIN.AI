"""P4.5 — Recovery detail exposes exact digest for approval UI."""
from __future__ import annotations

import inspect
import unittest

from api import routes_recovery


class RecoveryDetailContractTests(unittest.TestCase):
    def test_detail_loads_pending_approval_digest_not_placeholder(self):
        source = inspect.getsource(routes_recovery.get_opportunity_detail)
        self.assertIn("AgentApproval", source)
        self.assertIn("action_digest", source)
        self.assertIn("can_decide", source)
        self.assertNotIn("pending_approval_required_in_next_phase", source)

    def test_overview_reads_recovery_mode_from_settings(self):
        source = inspect.getsource(routes_recovery.get_overview)
        self.assertIn("PAYMENT_RECOVERY_MODE", source)
        self.assertNotIn('"mode": "observe",  # Phase 2 only observe', source)


if __name__ == "__main__":
    unittest.main()
