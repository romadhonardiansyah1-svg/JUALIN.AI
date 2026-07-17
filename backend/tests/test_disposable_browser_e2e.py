import unittest
from unittest.mock import patch


class DisposableBrowserE2ETests(unittest.TestCase):
    def test_report_requires_every_expected_real_stack_scenario(self):
        from scripts.run_disposable_browser_e2e import playwright_assertions

        report = {
            "suites": [{
                "specs": [{
                    "title": "real tenant switch",
                    "file": "auth-cache-and-proof.real.spec.js",
                    "tests": [{
                        "status": "expected",
                        "results": [{"status": "passed"}],
                    }],
                }],
            }],
        }

        assertions = playwright_assertions(
            report,
            {"real tenant switch"},
            expected_file="auth-cache-and-proof.real.spec.js",
        )

        self.assertEqual(assertions, [{
            "ok": True,
            "message": "Playwright passed: real tenant switch",
            "audit_code": "real_browser_runtime",
        }])

    def test_report_rejects_missing_scenario(self):
        from scripts.run_disposable_browser_e2e import playwright_assertions

        with self.assertRaises(RuntimeError):
            playwright_assertions({"suites": []}, {"missing"})

    def test_report_rejects_matching_title_from_another_file(self):
        from scripts.run_disposable_browser_e2e import playwright_assertions

        report = {
            "suites": [{
                "specs": [{
                    "title": "required title",
                    "file": "mocked.spec.js",
                    "tests": [{
                        "status": "expected",
                        "results": [{"status": "passed"}],
                    }],
                }],
            }],
        }
        with self.assertRaises(RuntimeError):
            playwright_assertions(
                report,
                {"required title"},
                expected_file="auth-cache-and-proof.real.spec.js",
            )

    def test_report_rejects_root_report_errors(self):
        from scripts.run_disposable_browser_e2e import playwright_assertions

        report = {"errors": [{"message": "reporter failure"}], "suites": []}
        with self.assertRaises(RuntimeError):
            playwright_assertions(report, set())

    def test_redis_readiness_retries_an_initial_not_ready_result(self):
        import json
        import subprocess
        import uuid

        from scripts.run_disposable_browser_e2e import _disposable_redis

        run_id = str(uuid.uuid4())
        container_id = "a" * 64
        name = f"jualin-test-redis-{uuid.UUID(run_id).hex}"
        inspected = {
            "Id": container_id,
            "Name": f"/{name}",
            "State": {"Running": True},
            "Config": {
                "Image": "redis:7-alpine",
                "Labels": {
                    "com.jualin.disposable": "true",
                    "com.jualin.test-run-id": run_id,
                    "com.jualin.resource": "redis-e2e",
                },
            },
            "Mounts": [],
            "NetworkSettings": {
                "Ports": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "49152"}]}
            },
        }
        ping_attempts = 0

        def docker(arguments, **_kwargs):
            nonlocal ping_attempts
            if arguments[0] == "run":
                return subprocess.CompletedProcess(arguments, 0, container_id, "")
            if arguments[0] == "inspect":
                return subprocess.CompletedProcess(arguments, 0, json.dumps([inspected]), "")
            if arguments[0] == "exec":
                ping_attempts += 1
                if ping_attempts == 1:
                    raise RuntimeError("redis not ready")
                return subprocess.CompletedProcess(arguments, 0, "PONG\n", "")
            if arguments[0] == "ps":
                self.assertIn(
                    "label=com.jualin.resource=redis-e2e",
                    arguments,
                )
                return subprocess.CompletedProcess(arguments, 0, f"{container_id}\n", "")
            if arguments[:3] == ["container", "rm", "--force"]:
                return subprocess.CompletedProcess(arguments, 0, container_id, "")
            raise AssertionError(f"unexpected docker command: {arguments[0]}")

        with patch("scripts.run_with_disposable_database._docker", side_effect=docker):
            with _disposable_redis(run_id) as redis_url:
                self.assertEqual(redis_url, "redis://127.0.0.1:49152/0")

        self.assertEqual(ping_attempts, 2)

    def test_redis_cleanup_does_not_mask_primary_failure(self):
        import json
        import subprocess
        import uuid

        from scripts.run_disposable_browser_e2e import _disposable_redis

        run_id = str(uuid.uuid4())
        container_id = "a" * 64
        name = f"jualin-test-redis-{uuid.UUID(run_id).hex}"
        inspected = {
            "Id": container_id,
            "Name": f"/{name}",
            "State": {"Running": True},
            "Config": {
                "Image": "redis:7-alpine",
                "Labels": {
                    "com.jualin.disposable": "true",
                    "com.jualin.test-run-id": run_id,
                    "com.jualin.resource": "redis-e2e",
                },
            },
            "Mounts": [],
            "NetworkSettings": {
                "Ports": {"6379/tcp": [{"HostIp": "127.0.0.1", "HostPort": "49152"}]}
            },
        }

        def docker(arguments, **_kwargs):
            if arguments[0] == "run":
                return subprocess.CompletedProcess(arguments, 0, container_id, "")
            if arguments[0] == "inspect":
                return subprocess.CompletedProcess(arguments, 0, json.dumps([inspected]), "")
            if arguments[0] == "exec":
                return subprocess.CompletedProcess(arguments, 0, "PONG\n", "")
            if arguments[0] == "ps":
                raise RuntimeError("synthetic teardown detail")
            raise AssertionError(f"unexpected docker command: {arguments[0]}")

        with patch("scripts.run_with_disposable_database._docker", side_effect=docker):
            with self.assertRaisesRegex(ValueError, "primary failure") as raised:
                with _disposable_redis(run_id):
                    raise ValueError("primary failure")

        self.assertEqual(
            getattr(raised.exception, "__notes__", []),
            ["Disposable Redis cleanup also failed; details withheld"],
        )
        self.assertNotIn("synthetic teardown detail", str(raised.exception))

    def test_process_cleanup_does_not_mask_primary_failure(self):
        from scripts.run_disposable_browser_e2e import _process

        process = unittest.mock.MagicMock()
        process.poll.return_value = None
        process.terminate.side_effect = RuntimeError("cleanup failure")
        with patch("scripts.run_disposable_browser_e2e.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(ValueError, "primary failure") as raised:
                with _process(
                    ["synthetic-command"],
                    cwd=unittest.mock.MagicMock(),
                    environment={},
                ):
                    raise ValueError("primary failure")

        self.assertTrue(getattr(raised.exception, "__notes__", []))

    def test_browser_artifact_is_unverified_when_source_identity_changes(self):
        import json
        import os
        import tempfile
        from pathlib import Path

        from scripts import run_disposable_browser_e2e as runner

        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td) / "proof-browser.json"
            with (
                patch.object(runner, "ARTIFACT", artifact),
                patch.dict(
                    os.environ,
                    {
                        "JUALIN_EVIDENCE_RUN_ID": "identity-change-run",
                        "JUALIN_PROOF_SEED": "42",
                    },
                    clear=False,
                ),
            ):
                runner._write_artifact(
                    [],
                    [],
                    "2026-07-17T00:00:00+00:00",
                    source_commit="abc",
                    source_identity_stable=False,
                )

            payload = json.loads(artifact.read_text(encoding="utf-8"))

        self.assertEqual(payload["commit_sha"], "abc")
        self.assertIs(payload["source_tree_clean"], False)
        self.assertEqual(payload["status"], "unverified")

    def test_frontend_environment_does_not_inherit_backend_authority(self):
        from scripts.run_disposable_browser_e2e import _frontend_environment

        source = {
            "PATH": "safe-path",
            "HOME": "safe-home",
            "CI": "true",
            "DATABASE_URL": "secret-dsn",
            "SECRET_KEY": "secret",
            "JWT_SECRET_KEY": "secret",
            "WHATSAPP_ACCESS_TOKEN": "secret",
            "NEXT_PUBLIC_API_URL": "https://production.example/api",
            "NEXT_PUBLIC_TRACKING_ID": "ambient-tracker",
        }
        environment = _frontend_environment(source, "http://127.0.0.1:8000")

        self.assertEqual(environment["PATH"], "safe-path")
        self.assertEqual(environment["CI"], "true")
        self.assertEqual(environment["INTERNAL_API_URL"], "http://127.0.0.1:8000")
        self.assertEqual(environment["NEXT_PUBLIC_API_URL"], "http://127.0.0.1:8000")
        self.assertNotIn("NEXT_PUBLIC_TRACKING_ID", environment)
        for forbidden in (
            "DATABASE_URL",
            "SECRET_KEY",
            "JWT_SECRET_KEY",
            "WHATSAPP_ACCESS_TOKEN",
        ):
            self.assertNotIn(forbidden, environment)

    def test_backend_environment_keeps_authority_but_drops_provider_credentials(self):
        from scripts.run_disposable_browser_e2e import _backend_environment

        source = {
            "PATH": "safe-path",
            "CI": "true",
            "DATABASE_URL": "postgresql://disposable-authority",
            "ENVIRONMENT": "test",
            "JUALIN_TEST_RUN_ID": "synthetic-run",
            "JUALIN_TEST_CONTAINER_ID": "synthetic-container",
            "JUALIN_TEST_SERVER_ADDRESS": "127.0.0.1",
            "JUALIN_EVIDENCE_RUN_ID": "evidence-run",
            "JUALIN_PROOF_SEED": "42",
            "WHATSAPP_ACCESS_TOKEN": "ambient-provider-secret",
            "LLM_API_KEY": "ambient-ai-secret",
            "PAYMENT_PROVIDER_SECRET": "ambient-payment-secret",
        }

        environment = _backend_environment(source)

        self.assertEqual(environment["DATABASE_URL"], source["DATABASE_URL"])
        self.assertEqual(environment["JUALIN_TEST_RUN_ID"], "synthetic-run")
        self.assertEqual(environment["JUALIN_EVIDENCE_RUN_ID"], "evidence-run")
        self.assertEqual(environment["WHATSAPP_ACCESS_TOKEN"], "")
        self.assertEqual(environment["LLM_API_KEY"], "")
        self.assertNotIn("PAYMENT_PROVIDER_SECRET", environment)

    def test_main_blocks_before_neutralizing_provider_credentials(self):
        from scripts import run_disposable_browser_e2e as runner

        with patch(
            "services.payment_recovery.proof.production_guard_blocks_proof_mode",
            return_value=(True, "real_whatsapp_credentials_present"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Proof runner safety guard blocked execution"):
                runner.main()

    def test_ci_invokes_real_e2e_through_disposable_database_runner(self):
        from pathlib import Path

        workflow = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "python -m scripts.run_with_disposable_database -- python -m scripts.run_disposable_browser_e2e",
            workflow,
        )

    def test_ci_real_job_cannot_upload_stale_browser_evidence(self):
        from pathlib import Path

        workflow = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("rm -f artifacts/proof-browser.json", workflow)
        self.assertIn(
            "- name: Upload real browser evidence\n        if: success()",
            workflow,
        )

    def test_ci_producers_remove_stale_artifacts_and_upload_only_verified_outputs(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github" / "workflows" / "deploy.yml").read_text(
            encoding="utf-8"
        )
        mocked_spec = (
            root / "frontend" / "e2e" / "auth-cache-and-proof.spec.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "rm -f artifacts/proof-backend.json artifacts/competition-evidence-status.json",
            workflow,
        )
        self.assertIn("rm -f artifacts/proof-browser.json", workflow)
        self.assertIn(
            "- name: Upload Proof Mode artifact\n        if: success()",
            workflow,
        )
        self.assertIn(
            "- name: Upload mocked browser artifact (unverified only)\n        if: success()",
            workflow,
        )
        self.assertIn("claims['proof_backend']['status']=='verified'", workflow)
        self.assertLess(
            workflow.index("- name: Python dependency audit"),
            workflow.index("- name: Upload Proof Mode artifact"),
        )
        self.assertLess(
            workflow.index("- name: Docker Compose config validation"),
            workflow.index("- name: Upload Proof Mode artifact"),
        )
        self.assertIn("- name: Validate mocked browser artifact policy", workflow)
        self.assertIn("artifact.api_mocking !== true", workflow)
        self.assertIn('api_mocking: true', mocked_spec)

    def test_guard_requires_disposable_runner_authority(self):
        from scripts.run_disposable_browser_e2e import assert_guarded_environment

        with patch.dict("os.environ", {"ENVIRONMENT": "test"}, clear=True):
            with self.assertRaises(RuntimeError):
                assert_guarded_environment()


if __name__ == "__main__":
    unittest.main()
