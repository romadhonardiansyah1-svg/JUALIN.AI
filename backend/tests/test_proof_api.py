"""P6.3 — Proof Mode API capability and redaction."""
from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException


class ProofApiContractTests(unittest.TestCase):
    def test_routes_registered_under_proof_prefix(self):
        import main

        paths = {getattr(r, "path", "") for r in main.app.routes}
        self.assertTrue(any(p.startswith("/api/proof") for p in paths))

    def test_non_admin_without_demo_flag_forbidden(self):
        from api.routes_proof import _require_proof_principal
        from models.user import UserRole

        user = SimpleNamespace(role=UserRole.SELLER, id=2)
        with self.assertRaises(HTTPException) as cm:
            _require_proof_principal(user)
        self.assertEqual(cm.exception.status_code, 403)

    def test_run_source_allowlists_backend_suite_only(self):
        from api import routes_proof

        source = inspect.getsource(routes_proof.ProofRunRequest)
        self.assertIn("backend", source)
        self.assertNotIn("arbitrary", source)


if __name__ == "__main__":
    unittest.main()
