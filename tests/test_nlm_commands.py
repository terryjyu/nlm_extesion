import subprocess
import unittest
from unittest.mock import patch

from nlm_extension.nlm_commands import CommandResult, NlmClient, NlmCommandError, NlmErrorKind


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def command_result(stdout="", stderr="", args=None, returncode=0, attempts=1):
    return CommandResult(args=args or ["nlm"], returncode=returncode, stdout=stdout, stderr=stderr, attempts=attempts)


class TestRunCommand(unittest.TestCase):
    @patch("nlm_extension.nlm_commands.time.sleep", return_value=None)
    @patch("nlm_extension.nlm_commands.subprocess.run")
    def test_run_command_retries_then_success(self, run_mock, _sleep_mock):
        run_mock.side_effect = [
            completed(["nlm"], returncode=2, stderr="transient error"),
            completed(["nlm"], returncode=0, stdout="ok"),
        ]

        client = NlmClient(retries=1)
        result = client.run_command(["ls"])

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(run_mock.call_count, 2)

    @patch("nlm_extension.nlm_commands.subprocess.run")
    def test_run_command_timeout_classification(self, run_mock):
        run_mock.side_effect = subprocess.TimeoutExpired(cmd=["nlm"], timeout=1)

        client = NlmClient(timeout_s=1, retries=0)
        with self.assertRaises(NlmCommandError) as ctx:
            client.run_command(["ls"])

        self.assertEqual(ctx.exception.kind, NlmErrorKind.TIMEOUT)

    @patch("nlm_extension.nlm_commands.subprocess.run")
    def test_run_command_auth_error_classification(self, run_mock):
        run_mock.return_value = completed(["nlm"], returncode=1, stderr="Authentication required. Run 'nlm auth'")

        client = NlmClient(retries=0)
        with self.assertRaises(NlmCommandError) as ctx:
            client.run_command(["ls"])

        self.assertEqual(ctx.exception.kind, NlmErrorKind.AUTH_SESSION)


class TestNlmOperations(unittest.TestCase):
    @patch.object(NlmClient, "run_command")
    def test_end_to_end_manifest_mapping(self, run_command_mock):
        run_command_mock.side_effect = [
            command_result(stdout="proj_abc123\n"),
            command_result(stdout="Adding source from file: paper.pdf\nsrc_555\n"),
            command_result(stdout="Creating audio overview for notebook proj_abc123...\n✅ Audio overview creation started. Use 'nlm audio-get' to check status.\n"),
            command_result(stdout="Audio overview is not ready yet. Try again in a few moments.\n", stderr="Fetching audio overview...\n"),
            command_result(stdout="Audio Overview:\n  Title: Weekly Summary\n  ID: audio_42\n  Ready: true\n", stderr="Fetching audio overview...\n"),
            command_result(stdout="Downloading audio overview for notebook proj_abc123...\n✅ Audio saved to: build/audio_overview_proj_abc123.wav\n  File size: 3.50 MB\n"),
        ]

        client = NlmClient()

        notebook_id = client.create_notebook("Demo")
        source_id = client.upload_pdf_source(notebook_id, "paper.pdf")
        _ = client.trigger_audio_overview(notebook_id, "concise overview")

        with patch("nlm_extension.nlm_commands.time.sleep", return_value=None):
            final_job = client.poll_overview_completion(notebook_id, interval_s=0.01, timeout_s=1)

        assets = client.download_audio_assets(notebook_id)
        manifest = client.manifest_entry(notebook_id=notebook_id, source_id=source_id, job=final_job, assets=assets)

        self.assertEqual(final_job.audio_id, "audio_42")
        self.assertEqual(manifest["audio_overview"]["status"], "completed")
        self.assertEqual(manifest["assets"][0]["format"], "wav")

    @patch.object(NlmClient, "run_command")
    def test_select_notebook_from_ls_output_by_title(self, run_command_mock):
        run_command_mock.return_value = command_result(
            stdout=(
                "Total notebooks: 1 (showing first 1)\n\n"
                "ID                                   TITLE                                      SOURCES LAST UPDATED\n"
                "12345678-1234-5678-9abc-def012345678 📙 My Notebook                              1       2025-09-17T01:58:50Z\n"
            )
        )
        client = NlmClient()

        selected = client.select_notebook("My Notebook")

        self.assertEqual(selected, "12345678-1234-5678-9abc-def012345678")

    @patch.object(NlmClient, "run_command")
    def test_parse_failure_when_audio_download_path_missing(self, run_command_mock):
        run_command_mock.return_value = command_result(stdout="Downloading audio overview...\n")
        client = NlmClient()

        with self.assertRaises(NlmCommandError) as ctx:
            client.download_audio_assets("proj_abc123")

        self.assertEqual(ctx.exception.kind, NlmErrorKind.PARSE_FAILURE)


if __name__ == "__main__":
    unittest.main()
