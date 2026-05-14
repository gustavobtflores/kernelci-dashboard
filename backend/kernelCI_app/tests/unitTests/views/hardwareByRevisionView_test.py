from http import HTTPStatus
from unittest.mock import patch

from django.test.testcases import SimpleTestCase
from rest_framework.test import APIRequestFactory

from kernelCI_app.views.hardwareByRevisionView import HardwareByRevisionView


class TestHardwareByRevisionView(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = HardwareByRevisionView()
        self.url = "/hardware-by-revision"
        self.required_query_params = {
            "origin": "origin1",
            "tree_name": "mainline",
            "git_repository_url": "https://example.com/linux.git",
            "git_repository_branch": "master",
            "git_commit_hash": "abc123",
        }

    @patch(
        "kernelCI_app.views.hardwareByRevisionView.get_hardware_listing_data_by_revision"
    )
    def test_get_hardware_listing_by_revision_success(
        self, mock_get_hardware_listing_data_by_revision
    ):
        mock_get_hardware_listing_data_by_revision.return_value = [
            ("platform1", ["hardware1"], *range(22)),
        ]

        request = self.factory.get(self.url, self.required_query_params)
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.data["hardware"][0]["platform"], "platform1")

    def test_get_hardware_listing_by_revision_missing_query_params_returns_bad_request(
        self,
    ):
        request = self.factory.get(self.url, {"origin": "origin1"})
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn("tree_name", response.data)
        self.assertIn("git_repository_url", response.data)
        self.assertIn("git_repository_branch", response.data)
        self.assertIn("git_commit_hash", response.data)

    @patch(
        "kernelCI_app.views.hardwareByRevisionView.get_hardware_listing_data_by_revision"
    )
    def test_get_hardware_listing_by_revision_empty_response(
        self, mock_get_hardware_listing_data_by_revision
    ):
        mock_get_hardware_listing_data_by_revision.return_value = []

        request = self.factory.get(self.url, self.required_query_params)
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.data, {"hardware": []})

    @patch(
        "kernelCI_app.views.hardwareByRevisionView.get_hardware_listing_data_by_revision"
    )
    def test_get_hardware_listing_by_revision_sanitize_validation_error_returns_internal_server_error(
        self, mock_get_hardware_listing_data_by_revision
    ):
        mock_get_hardware_listing_data_by_revision.return_value = [
            (None, "hardware1", *range(22)),
        ]

        request = self.factory.get(self.url, self.required_query_params)
        response = self.view.get(request)

        self.assertEqual(response.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn("platform", response.data)
