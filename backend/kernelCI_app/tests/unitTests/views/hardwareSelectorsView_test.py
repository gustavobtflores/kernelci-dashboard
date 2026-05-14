from datetime import datetime
from http import HTTPStatus
from unittest.mock import patch

from django.test.testcases import SimpleTestCase
from rest_framework.test import APIRequestFactory

from kernelCI_app.constants.general import DEFAULT_ORIGIN
from kernelCI_app.views.hardwareSelectorsView import HardwareSelectorsView


class TestHardwareSelectorsView(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = HardwareSelectorsView()
        self.url = "/hardware/selectors"

    @patch("kernelCI_app.views.hardwareSelectorsView.get_hardware_selectors")
    def test_get_hardware_selectors_success(self, mock_get_hardware_selectors):
        mock_get_hardware_selectors.return_value = [
            {
                "tree_name": "mainline",
                "git_repository_url": "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
                "git_repository_branch": "master",
                "git_commit_hash": "abc123",
                "git_commit_name": "v6.12-rc1",
                "latest_start_time": datetime(2026, 1, 1, 10, 0, 0),
                "branch_latest_start_time": datetime(2026, 1, 1, 10, 0, 0),
            }
        ]

        request = self.factory.get(self.url, {"origin": "origin1"})
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.data["trees"][0]["tree_name"], "mainline")
        self.assertEqual(
            response.data["trees"][0]["branches"][0]["revisions"][0]["git_commit_hash"],
            "abc123",
        )
        mock_get_hardware_selectors.assert_called_once_with(origin="origin1")

    @patch("kernelCI_app.views.hardwareSelectorsView.get_hardware_selectors")
    def test_get_hardware_selectors_defaults_origin(self, mock_get_hardware_selectors):
        mock_get_hardware_selectors.return_value = []

        request = self.factory.get(self.url)
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.data, {"trees": []})
        mock_get_hardware_selectors.assert_called_once_with(origin=DEFAULT_ORIGIN)

    @patch("kernelCI_app.views.hardwareSelectorsView.get_hardware_selectors")
    def test_get_hardware_selectors_empty_response(self, mock_get_hardware_selectors):
        mock_get_hardware_selectors.return_value = []

        request = self.factory.get(self.url, {"origin": "origin1"})
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.data, {"trees": []})

    @patch("kernelCI_app.views.hardwareSelectorsView.get_hardware_selectors")
    def test_get_hardware_selectors_sanitize_validation_error_returns_internal_server_error(
        self, mock_get_hardware_selectors
    ):
        mock_get_hardware_selectors.return_value = [
            {
                "tree_name": "mainline",
                "git_repository_url": "https://example.com/linux.git",
                "git_repository_branch": "master",
                "git_commit_hash": None,
                "git_commit_name": "v6.12-rc1",
                "latest_start_time": datetime(2026, 1, 1, 10, 0, 0),
                "branch_latest_start_time": datetime(2026, 1, 1, 10, 0, 0),
            }
        ]

        request = self.factory.get(self.url, {"origin": "origin1"})
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn("git_commit_hash", response.data)
