"""Unit tests for the isolated P0.0a PostgreSQL lifecycle runner."""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import unittest
from unittest.mock import MagicMock, call, patch


RUN_ID = "3f2504e0-4f89-4d3a-9a0c-0305e82c3301"
TOKEN = RUN_ID.replace("-", "")
CONTAINER_ID = "a" * 64
SERVER_ADDRESS = "172.19.0.2"


class DisposableDatabaseRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = importlib.import_module("scripts.run_with_disposable_database")

    def _authority(self):
        with patch.object(
            self.runner.secrets,
            "token_urlsafe",
            side_effect=("bootstrap-secret-" + "a" * 32, "role-secret-" + "b" * 32),
        ):
            authority = self.runner.new_authority(RUN_ID)
        return authority.with_runtime(
            container_id=CONTAINER_ID,
            server_address=SERVER_ADDRESS,
            host_port=55432,
            network_id="b" * 64,
        )

    def _inspect(self, authority, **label_overrides):
        labels = {
            "com.docker.compose.project": authority.project_name,
            "com.docker.compose.service": "postgres",
            "com.jualin.disposable": "true",
            "com.jualin.test-run-id": authority.run_id,
        }
        labels.update(label_overrides)
        return {
            "Id": authority.container_id,
            "Config": {
                "Image": "pgvector/pgvector:pg16",
                "Labels": labels,
            },
            "State": {"Status": "running", "Health": {"Status": "healthy"}},
            "HostConfig": {
                "Tmpfs": {
                    "/var/lib/postgresql/data": "rw,nosuid,noexec",
                }
            },
            "Mounts": [],
            "NetworkSettings": {
                "Ports": {
                    "5432/tcp": [
                        {"HostIp": "127.0.0.1", "HostPort": str(authority.host_port)}
                    ]
                },
                "Networks": {
                    f"{authority.project_name}_default": {
                        "IPAddress": authority.server_address,
                        "NetworkID": authority.network_id,
                    }
                },
            },
        }

    def _network(self, authority, *, attached=True):
        containers = {authority.container_id: {}} if attached else {}
        return {
            "Name": f"{authority.project_name}_default",
            "Id": authority.network_id,
            "Driver": "bridge",
            "Scope": "local",
            "Internal": False,
            "Attachable": False,
            "Ingress": False,
            "Options": {
                "com.docker.network.bridge.host_binding_ipv4": "127.0.0.1",
            },
            "Labels": {
                "com.docker.compose.project": authority.project_name,
                "com.docker.compose.network": "default",
                "com.jualin.disposable": "true",
                "com.jualin.test-run-id": authority.run_id,
            },
            "Containers": containers,
        }

    def test_authority_uses_run_bound_names_and_redacts_secrets(self) -> None:
        authority = self._authority()

        self.assertEqual(authority.project_name, f"jualin-test-{TOKEN}")
        self.assertEqual(authority.database_name, f"jualin_test_{TOKEN}")
        self.assertEqual(authority.role_name, f"jualin_test_role_{TOKEN}")
        self.assertNotIn(authority.bootstrap_password, repr(authority))
        self.assertNotIn(authority.role_password, repr(authority))
        self.assertNotIn(authority.role_password, str(authority))

    def test_compose_configuration_is_ephemeral_and_loopback_only(self) -> None:
        compose_path = pathlib.Path(self.runner.COMPOSE_FILE)
        content = compose_path.read_text(encoding="utf-8")

        self.assertIn('127.0.0.1::5432', content)
        self.assertIn("tmpfs:", content)
        self.assertNotIn("volumes:", content)
        self.assertIn("driver: bridge", content)
        self.assertIn("internal: false", content)
        self.assertIn("attachable: false", content)
        self.assertIn("com.docker.network.bridge.host_binding_ipv4", content)
        self.assertIn("com.jualin.test-run-id", content)
        self.assertIn("pgvector/pgvector:pg16", content)

    @patch("scripts.run_with_disposable_database.subprocess.run")
    def test_docker_environment_is_pinned_to_an_inspected_local_endpoint(
        self, mock_run
    ) -> None:
        for endpoint in (
            "unix:///var/run/docker.sock",
            "npipe:////./pipe/docker_engine",
        ):
            with self.subTest(endpoint=endpoint), patch.dict(
                os.environ, {}, clear=True
            ):
                mock_run.reset_mock()
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=json.dumps(endpoint),
                )

                environment = self.runner._local_docker_environment()

                self.assertEqual(environment["DOCKER_HOST"], endpoint)
                self.assertNotIn("DOCKER_CONTEXT", environment)
                self.assertNotIn("DOCKER_TLS", environment)
                self.assertNotIn("DOCKER_TLS_VERIFY", environment)
                self.assertNotIn("DOCKER_CERT_PATH", environment)
                mock_run.assert_called_once()
                self.assertEqual(
                    mock_run.call_args.args[0],
                    [
                        "docker",
                        "context",
                        "inspect",
                        "--format",
                        "{{json .Endpoints.docker.Host}}",
                    ],
                )

    @patch("scripts.run_with_disposable_database.subprocess.run")
    def test_docker_preflight_rejects_remote_contexts_and_ambient_overrides(
        self, mock_run
    ) -> None:
        for endpoint in (
            "tcp://production.example:2376",
            "ssh://operator@production.example",
        ):
            with self.subTest(endpoint=endpoint), patch.dict(
                os.environ, {}, clear=True
            ):
                mock_run.reset_mock()
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=json.dumps(endpoint),
                )

                with self.assertRaises(self.runner.SafetyError):
                    self.runner._local_docker_environment()

        unsafe_environment = {
            "DOCKER_HOST": "tcp://production.example:2376",
            "DOCKER_CONTEXT": "production",
            "DOCKER_TLS": "1",
            "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CERT_PATH": "/production/certificates",
        }
        for key, value in unsafe_environment.items():
            with self.subTest(variable=key), patch.dict(
                os.environ, {key: value}, clear=True
            ):
                mock_run.reset_mock()

                with self.assertRaises(self.runner.SafetyError):
                    self.runner._local_docker_environment()

                mock_run.assert_not_called()

    @patch("scripts.run_with_disposable_database.subprocess.run")
    def test_docker_command_cannot_reintroduce_a_context_override(
        self, mock_run
    ) -> None:
        endpoint = "npipe:////./pipe/docker_engine"
        mock_run.side_effect = (
            MagicMock(returncode=0, stdout=json.dumps(endpoint)),
            MagicMock(returncode=0, stdout="safe"),
        )
        requested_environment = {
            "DOCKER_CONTEXT": "production",
            "DOCKER_HOST": "tcp://production.example:2376",
            "DOCKER_TLS_VERIFY": "1",
            "JUALIN_TEST_RUN_ID": RUN_ID,
        }
        with patch.dict(os.environ, {}, clear=True):
            result = self.runner._docker(
                ["version"], environment=requested_environment
            )

        self.assertEqual(result.stdout, "safe")
        actual_environment = mock_run.call_args_list[1].kwargs["env"]
        self.assertEqual(actual_environment["DOCKER_HOST"], endpoint)
        self.assertEqual(actual_environment["JUALIN_TEST_RUN_ID"], RUN_ID)
        self.assertNotIn("DOCKER_CONTEXT", actual_environment)
        self.assertNotIn("DOCKER_TLS_VERIFY", actual_environment)

    def test_ci_full_backend_suite_cannot_bypass_disposable_runner(self) -> None:
        workflow = pathlib.Path(__file__).parents[2] / ".github" / "workflows" / "deploy.yml"
        content = workflow.read_text(encoding="utf-8")
        self.assertIn(
            "python -m scripts.run_with_disposable_database -- "
            "python -m unittest discover -s tests -v",
            content,
        )

    def test_readme_db_commands_use_disposable_runner(self) -> None:
        readme = pathlib.Path(__file__).parents[2] / "README.md"
        content = readme.read_text(encoding="utf-8")

        self.assertIn(
            "-m scripts.run_with_disposable_database --cwd $repo -- "
            "$py -m alembic -c .\\alembic.ini upgrade head",
            content,
        )
        self.assertIn(
            "-m scripts.run_with_disposable_database -- "
            "$py -m unittest discover -s tests -v",
            content,
        )
        self.assertNotIn(
            "    ..\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v",
            content,
        )
        self.assertNotIn(
            "    .venv\\Scripts\\python.exe -m alembic -c alembic.ini upgrade head",
            content,
        )

    @patch("scripts.run_with_disposable_database.subprocess.run")
    @patch("scripts.run_with_disposable_database.connect_and_verify")
    def test_target_is_guarded_and_receives_exact_authority(
        self, mock_guard, mock_run
    ) -> None:
        authority = self._authority()
        mock_run.return_value = MagicMock(returncode=7)
        calls = MagicMock()
        calls.attach_mock(mock_guard, "guard")
        calls.attach_mock(mock_run, "run")

        result = self.runner.run_target(
            authority,
            ["python", "-m", "unittest"],
            cwd=pathlib.Path("."),
        )

        self.assertEqual(result, 7)
        self.assertEqual(calls.mock_calls[0], call.guard(authority.dsn, RUN_ID))
        kwargs = mock_run.call_args.kwargs
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["env"]["ENVIRONMENT"], "test")
        self.assertEqual(kwargs["env"]["DATABASE_URL"], authority.dsn)
        self.assertEqual(kwargs["env"]["JUALIN_TEST_RUN_ID"], RUN_ID)
        self.assertEqual(
            kwargs["env"]["JUALIN_TEST_CONTAINER_ID"], authority.container_id
        )
        self.assertEqual(
            kwargs["env"]["JUALIN_TEST_SERVER_ADDRESS"], authority.server_address
        )

    def test_container_inspection_requires_exact_labels_endpoint_and_no_mounts(self) -> None:
        authority = self._authority()
        self.runner.assert_container_authority(authority, self._inspect(authority))

        tmpfs_reported_as_mount = self._inspect(authority)
        tmpfs_reported_as_mount["Mounts"] = [
            {
                "Type": "tmpfs",
                "Destination": "/var/lib/postgresql/data",
            }
        ]
        self.runner.assert_container_authority(authority, tmpfs_reported_as_mount)

        missing_tmpfs = self._inspect(authority)
        missing_tmpfs["HostConfig"]["Tmpfs"] = {}
        with self.assertRaises(self.runner.SafetyError):
            self.runner.assert_container_authority(authority, missing_tmpfs)

        bad_label = self._inspect(
            authority, **{"com.docker.compose.project": "ambient-project"}
        )
        with self.assertRaises(self.runner.SafetyError):
            self.runner.assert_container_authority(authority, bad_label)

        bad_mount = self._inspect(authority)
        bad_mount["Mounts"] = [{"Type": "volume", "Name": "ambient-data"}]
        with self.assertRaises(self.runner.SafetyError):
            self.runner.assert_container_authority(authority, bad_mount)

    @patch("scripts.run_with_disposable_database._docker")
    @patch("scripts.run_with_disposable_database._inspect_container")
    def test_teardown_refuses_before_remove_when_resource_label_mismatches(
        self, mock_inspect, mock_docker
    ) -> None:
        authority = self._authority()
        mock_inspect.return_value = self._inspect(
            authority, **{"com.jualin.test-run-id": "foreign-run"}
        )

        with self.assertRaises(self.runner.SafetyError):
            self.runner.verify_and_remove(authority)

        mock_docker.assert_not_called()

    @patch("scripts.run_with_disposable_database._docker")
    def test_network_enumeration_requires_full_resource_ids(self, mock_docker) -> None:
        authority = self._authority()
        mock_docker.return_value = MagicMock(stdout=f"{authority.network_id}\n")

        actual = self.runner._project_resource_ids(authority, "network")

        self.assertEqual(actual, [authority.network_id])
        mock_docker.assert_called_once_with(
            [
                "network",
                "ls",
                "--no-trunc",
                "--quiet",
                "--filter",
                f"label=com.docker.compose.project={authority.project_name}",
            ]
        )

    @patch("scripts.run_with_disposable_database._docker")
    def test_network_authority_requires_exact_local_bridge(self, mock_docker) -> None:
        authority = self._authority()
        network = self._network(authority)
        mock_docker.return_value = MagicMock(stdout=json.dumps([network]))
        self.runner._assert_network_authority(authority)

        unsafe_variants = (
            {"Name": "ambient_default"},
            {"Driver": "overlay"},
            {"Scope": "swarm"},
            {"Internal": True},
            {"Attachable": True},
            {"Ingress": True},
            {"Options": {}},
        )
        for override in unsafe_variants:
            with self.subTest(override=override):
                invalid = self._network(authority)
                invalid.update(override)
                mock_docker.return_value = MagicMock(stdout=json.dumps([invalid]))
                with self.assertRaises(self.runner.SafetyError):
                    self.runner._assert_network_authority(authority)

        for label, value in (
            ("com.docker.compose.project", "ambient-project"),
            ("com.jualin.disposable", None),
            ("com.jualin.test-run-id", "foreign-run"),
        ):
            with self.subTest(label=label):
                invalid = self._network(authority)
                if value is None:
                    invalid["Labels"].pop(label)
                else:
                    invalid["Labels"][label] = value
                mock_docker.return_value = MagicMock(stdout=json.dumps([invalid]))
                with self.assertRaises(self.runner.SafetyError):
                    self.runner._assert_network_authority(authority)

    @patch("scripts.run_with_disposable_database._assert_network_authority")
    @patch("scripts.run_with_disposable_database._inspect_container")
    @patch("scripts.run_with_disposable_database._compose")
    def test_start_verifies_network_authority_before_returning_runtime(
        self, mock_compose, mock_inspect, mock_network
    ) -> None:
        authority = self.runner.new_authority(RUN_ID)
        runtime = authority.with_runtime(
            container_id=CONTAINER_ID,
            server_address=SERVER_ADDRESS,
            host_port=55432,
            network_id="b" * 64,
        )
        mock_compose.side_effect = (
            MagicMock(stdout=""),
            MagicMock(stdout=""),
            MagicMock(stdout=f"{runtime.container_id}\n"),
        )
        mock_inspect.return_value = self._inspect(runtime)

        actual = self.runner._start_container(authority)

        self.assertEqual(actual, runtime)
        mock_network.assert_called_once_with(runtime)

    @patch("scripts.run_with_disposable_database._docker")
    @patch("scripts.run_with_disposable_database._project_resource_ids")
    @patch("scripts.run_with_disposable_database._inspect_container")
    @patch("scripts.run_with_disposable_database._compose")
    def test_start_failure_removes_only_verified_preprovision_resources(
        self, mock_compose, mock_inspect, mock_resources, mock_docker
    ) -> None:
        authority = self.runner.new_authority(RUN_ID)
        runtime = authority.with_runtime(
            container_id=CONTAINER_ID,
            server_address=SERVER_ADDRESS,
            host_port=55432,
            network_id="b" * 64,
        )
        invalid_container = self._inspect(runtime)
        invalid_container["NetworkSettings"]["Ports"]["5432/tcp"] = []
        mock_compose.side_effect = (
            MagicMock(stdout=""),
            MagicMock(stdout=""),
            MagicMock(stdout=f"{runtime.container_id}\n"),
        )
        mock_inspect.side_effect = (invalid_container, invalid_container)
        mock_resources.side_effect = (
            [runtime.container_id],
            [runtime.network_id],
            [],
            [],
            [],
            [],
        )
        mock_docker.side_effect = (
            MagicMock(stdout=json.dumps([self._network(runtime)])),
            MagicMock(stdout=""),
            MagicMock(stdout=json.dumps([self._network(runtime, attached=False)])),
            MagicMock(stdout=""),
        )

        with self.assertRaises(self.runner.SafetyError):
            self.runner._start_container(authority)

        self.assertIn(
            call(["container", "rm", "--force", runtime.container_id]),
            mock_docker.call_args_list,
        )
        self.assertEqual(
            mock_docker.call_args_list[-1],
            call(["network", "rm", runtime.network_id]),
        )

    @patch(
        "scripts.run_with_disposable_database._remove_preprovisioned_project",
        side_effect=RuntimeError("synthetic cleanup detail"),
    )
    @patch(
        "scripts.run_with_disposable_database._compose",
        side_effect=(MagicMock(stdout=""), RuntimeError("primary startup failure")),
    )
    def test_start_cleanup_does_not_mask_primary_failure(
        self, mock_compose, mock_cleanup
    ) -> None:
        authority = self.runner.new_authority(RUN_ID)

        with self.assertRaisesRegex(RuntimeError, "primary startup failure") as raised:
            self.runner._start_container(authority)

        self.assertEqual(
            getattr(raised.exception, "__notes__", []),
            ["Disposable database startup cleanup also failed; details withheld"],
        )
        self.assertNotIn("synthetic cleanup detail", str(raised.exception))
        mock_cleanup.assert_called_once_with(authority)

    @patch("scripts.run_with_disposable_database.psycopg2.connect")
    def test_provision_installs_vector_as_bootstrap_before_role_handoff(
        self, mock_connect
    ) -> None:
        authority = self._authority()
        admin_connection = MagicMock()
        extension_connection = MagicMock()
        role_connection = MagicMock()
        admin_cursor = admin_connection.cursor.return_value
        extension_cursor = extension_connection.cursor.return_value
        mock_connect.side_effect = (
            admin_connection,
            extension_connection,
            role_connection,
        )

        self.runner._provision_database(authority)

        self.assertEqual(mock_connect.call_count, 3)
        bootstrap_call, extension_call, role_call = mock_connect.call_args_list
        self.assertEqual(bootstrap_call.kwargs["dbname"], authority.bootstrap_database)
        self.assertEqual(bootstrap_call.kwargs["user"], authority.bootstrap_role)
        self.assertEqual(extension_call.kwargs["dbname"], authority.database_name)
        self.assertEqual(extension_call.kwargs["user"], authority.bootstrap_role)
        self.assertEqual(role_call.kwargs["dbname"], authority.database_name)
        self.assertEqual(role_call.kwargs["user"], authority.role_name)
        extension_cursor.execute.assert_called_once_with(
            "CREATE EXTENSION IF NOT EXISTS vector"
        )
        self.assertTrue(extension_connection.autocommit)
        self.assertFalse(role_connection.autocommit)
        role_connection.commit.assert_called_once_with()
        self.assertGreaterEqual(admin_cursor.execute.call_count, 3)

    @patch("scripts.run_with_disposable_database.psycopg2.connect")
    def test_provision_failure_never_commits_partial_sentinel(
        self, mock_connect
    ) -> None:
        authority = self._authority()
        admin_connection = MagicMock()
        extension_connection = MagicMock()
        role_connection = MagicMock()
        role_cursor = role_connection.cursor.return_value
        role_cursor.execute.side_effect = (
            None,
            None,
            RuntimeError("sentinel insert failed"),
        )
        mock_connect.side_effect = (
            admin_connection,
            extension_connection,
            role_connection,
        )

        with self.assertRaises(self.runner.SafetyError):
            self.runner._provision_database(authority)

        role_connection.commit.assert_not_called()
        role_connection.close.assert_called_once_with()

    @patch("scripts.run_with_disposable_database._docker")
    @patch("scripts.run_with_disposable_database.connect_and_verify")
    @patch("scripts.run_with_disposable_database._assert_network_authority")
    @patch("scripts.run_with_disposable_database._project_resource_ids")
    @patch("scripts.run_with_disposable_database._inspect_container")
    def test_teardown_never_removes_when_sentinel_recheck_fails(
        self,
        mock_inspect,
        mock_resources,
        mock_network,
        mock_guard,
        mock_docker,
    ) -> None:
        authority = self._authority()
        mock_inspect.return_value = self._inspect(authority)
        mock_resources.side_effect = (
            [authority.container_id],
            [authority.network_id],
            [],
        )
        mock_guard.side_effect = SystemExit(2)

        with self.assertRaises(SystemExit):
            self.runner.verify_and_remove(authority)

        mock_network.assert_called_once_with(authority)
        mock_docker.assert_not_called()

    @patch("scripts.run_with_disposable_database.verify_and_remove")
    @patch("scripts.run_with_disposable_database.run_target", return_value=9)
    @patch("scripts.run_with_disposable_database._provision_database")
    @patch("scripts.run_with_disposable_database._start_container")
    def test_nonzero_target_still_runs_verified_teardown(
        self, mock_start, mock_provision, mock_target, mock_teardown
    ) -> None:
        authority = self._authority()
        mock_start.return_value = authority

        result = self.runner.run_command(["python", "-m", "unittest"])

        self.assertEqual(result, 9)
        mock_provision.assert_called_once_with(authority)
        mock_target.assert_called_once()
        mock_teardown.assert_called_once_with(authority)

    @patch(
        "scripts.run_with_disposable_database.verify_and_remove",
        side_effect=RuntimeError("teardown failed"),
    )
    @patch("scripts.run_with_disposable_database.run_target", return_value=9)
    @patch("scripts.run_with_disposable_database._provision_database")
    @patch("scripts.run_with_disposable_database._start_container")
    def test_nonzero_target_and_teardown_failure_report_both_outcomes(
        self, mock_start, mock_provision, mock_target, mock_teardown
    ) -> None:
        authority = self._authority()
        mock_start.return_value = authority

        with self.assertRaisesRegex(
            self.runner.SafetyError,
            "Target exited with code 9; verified teardown also failed",
        ):
            self.runner.run_command(["python", "-m", "unittest"])

        mock_provision.assert_called_once_with(authority)
        mock_target.assert_called_once()
        mock_teardown.assert_called_once_with(authority)

    @patch("scripts.run_with_disposable_database.verify_and_remove")
    @patch("scripts.run_with_disposable_database._provision_database")
    @patch("scripts.run_with_disposable_database._start_container")
    def test_empty_command_is_rejected_before_container_start(
        self, mock_start, mock_provision, mock_teardown
    ) -> None:
        with self.assertRaises(self.runner.SafetyError):
            self.runner.run_command([])

        mock_start.assert_not_called()
        mock_provision.assert_not_called()
        mock_teardown.assert_not_called()

    @patch(
        "scripts.run_with_disposable_database._remove_preprovisioned_project",
        create=True,
    )
    @patch("scripts.run_with_disposable_database.verify_and_remove")
    @patch("scripts.run_with_disposable_database.run_target")
    @patch(
        "scripts.run_with_disposable_database._provision_database",
        side_effect=RuntimeError("provision failed"),
    )
    @patch("scripts.run_with_disposable_database._start_container")
    def test_provision_failure_uses_preprovision_cleanup_without_target(
        self,
        mock_start,
        mock_provision,
        mock_target,
        mock_teardown,
        mock_preprovision_cleanup,
    ) -> None:
        authority = self._authority()
        mock_start.return_value = authority

        with self.assertRaises(RuntimeError):
            self.runner.run_command(["python", "-m", "unittest"])

        mock_target.assert_not_called()
        mock_teardown.assert_not_called()
        mock_preprovision_cleanup.assert_called_once_with(authority)


if __name__ == "__main__":
    unittest.main()
