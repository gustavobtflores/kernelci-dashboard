from http import HTTPStatus

from drf_spectacular.utils import extend_schema
from pydantic import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from kernelCI_app.queries.hardware import get_hardware_listing_data_by_revision
from kernelCI_app.typeModels.hardwareListing import (
    HardwareItem,
    HardwareListingResponse,
)
from kernelCI_app.typeModels.hardwareListingByRevision import (
    HardwareListingByRevisionQueryParams,
    HardwareListingByRevisionQueryParamsDocumentationOnly,
)


class HardwareByRevisionView(APIView):
    def _sanitize_records(self, hardwares_raw: list[tuple]) -> list[HardwareItem]:
        hardwares = []
        for hardware in hardwares_raw:
            hardwares.append(
                HardwareItem(
                    platform=hardware[0],
                    hardware=hardware[1],
                    build_status_summary={
                        "PASS": hardware[2],
                        "FAIL": hardware[3],
                        "NULL": hardware[4],
                        "ERROR": hardware[5],
                        "MISS": hardware[6],
                        "DONE": hardware[7],
                        "SKIP": hardware[8],
                    },
                    boot_status_summary={
                        "PASS": hardware[9],
                        "FAIL": hardware[10],
                        "NULL": hardware[11],
                        "ERROR": hardware[12],
                        "MISS": hardware[13],
                        "DONE": hardware[14],
                        "SKIP": hardware[15],
                    },
                    test_status_summary={
                        "PASS": hardware[16],
                        "FAIL": hardware[17],
                        "NULL": hardware[18],
                        "ERROR": hardware[19],
                        "MISS": hardware[20],
                        "DONE": hardware[21],
                        "SKIP": hardware[22],
                    },
                )
            )

        return hardwares

    @extend_schema(
        parameters=[HardwareListingByRevisionQueryParamsDocumentationOnly],
        responses=HardwareListingResponse,
    )
    def get(self, request: Request):
        try:
            query_params = HardwareListingByRevisionQueryParams(
                origin=request.GET.get("origin"),
                tree_name=request.GET.get("tree_name"),
                git_repository_url=request.GET.get("git_repository_url"),
                git_repository_branch=request.GET.get("git_repository_branch"),
                git_commit_hash=request.GET.get("git_commit_hash"),
            )
        except ValidationError as e:
            return Response(data=e.json(), status=HTTPStatus.BAD_REQUEST)

        hardwares_raw = get_hardware_listing_data_by_revision(
            origin=query_params.origin,
            tree_name=query_params.tree_name,
            git_repository_url=query_params.git_repository_url,
            git_repository_branch=query_params.git_repository_branch,
            git_commit_hash=query_params.git_commit_hash,
        )

        try:
            sanitized_records = self._sanitize_records(hardwares_raw=hardwares_raw)
            result = HardwareListingResponse(hardware=sanitized_records)
        except ValidationError as e:
            return Response(data=e.json(), status=HTTPStatus.INTERNAL_SERVER_ERROR)

        return Response(data=result.model_dump(), status=HTTPStatus.OK)
