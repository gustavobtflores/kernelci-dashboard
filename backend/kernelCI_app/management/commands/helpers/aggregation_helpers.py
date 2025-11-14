from datetime import datetime
import math

from django.db import connection

from kernelCI_app.constants.general import MAESTRO_DUMMY_BUILD_PREFIX
from kernelCI_app.constants.ingester import INGEST_BATCH_SIZE
from kernelCI_app.models import (
    BuildStatusByHardware,
    Builds,
    NewBuild,
    NewTest,
    Tests,
)
from kernelCI_app.utils import is_boot


def ceil_to_next_half_hour(dt_input: str) -> int:
    half_hour_in_seconds = 1800
    timestamp = datetime.fromisoformat(dt_input).timestamp()
    return math.ceil(timestamp / half_hour_in_seconds) * half_hour_in_seconds


def convert_test(t: Tests) -> NewTest:
    is_boot_test = is_boot(t.path)
    start_time = ceil_to_next_half_hour(t.start_time)
    return NewTest(
        test_id=t.id,
        build_id=t.build_id,
        test_origin=t.origin,
        test_platform=t.environment_misc.get("platform"),
        test_compatible=t.environment_compatible,
        status=t.status,
        is_boot=is_boot_test,
        start_time=start_time,
    )


def convert_to_build_status_by_hardware(test: NewTest) -> BuildStatusByHardware:
    return BuildStatusByHardware(
        hardware_origin=test.test_origin,
        hardware_platform=test.test_platform,
        build_id=test.build_id,
    )


def prepare_build_status_by_hardware(
    tests: list[NewTest],
) -> list[BuildStatusByHardware]:
    return [convert_to_build_status_by_hardware(test) for test in tests]


def aggregate_hardware_status_data(tests: list[NewTest]) -> dict:
    aggregated_data = {}

    for test in tests:
        pass_count = 1 if test.status == "PASS" else 0
        failed_count = 1 if test.status == "FAIL" else 0
        inc_count = 1 if test.status not in ("PASS", "FAIL") else 0

        key = (test.test_origin, test.test_platform, test.build_id, test.start_time)

        if key not in aggregated_data:
            aggregated_data[key] = {
                "hardware_origin": test.test_origin,
                "hardware_platform": test.test_platform,
                "build_id": test.build_id,
                "date": test.start_time,
                "compatibles": test.test_compatible,
                "boot_pass": 0,
                "boot_failed": 0,
                "boot_inc": 0,
                "test_pass": 0,
                "test_failed": 0,
                "test_inc": 0,
            }

        if aggregated_data[key]["compatibles"] is None and test.test_compatible:
            aggregated_data[key]["compatibles"] = test.test_compatible

        if test.is_boot:
            aggregated_data[key]["boot_pass"] += pass_count
            aggregated_data[key]["boot_failed"] += failed_count
            aggregated_data[key]["boot_inc"] += inc_count
        else:
            aggregated_data[key]["test_pass"] += pass_count
            aggregated_data[key]["test_failed"] += failed_count
            aggregated_data[key]["test_inc"] += inc_count

    return aggregated_data


def convert_build(b: Builds) -> NewBuild:
    return NewBuild(
        build_id=b.id,
        checkout_id=b.checkout_id,
        build_origin=b.origin,
        status=b.status,
    )


def aggregate_builds_status(builds_instances: list[Builds]) -> None:
    builds_filtered = (
        b for b in builds_instances if not b.id.startswith(MAESTRO_DUMMY_BUILD_PREFIX)
    )

    builds_to_insert = list(convert_build(b) for b in builds_filtered)

    build_ids_to_insert = [b.build_id for b in builds_to_insert]
    existing_build_ids = set(
        NewBuild.objects.filter(build_id__in=build_ids_to_insert).values_list(
            "build_id", flat=True
        )
    )

    new_builds_only = [
        b for b in builds_to_insert if b.build_id not in existing_build_ids
    ]

    if new_builds_only:
        NewBuild.objects.bulk_create(
            new_builds_only,
            batch_size=INGEST_BATCH_SIZE,
            ignore_conflicts=True,
        )

        build_status_map = {build.build_id: build.status for build in new_builds_only}

        build_statuses_by_hardware = BuildStatusByHardware.objects.filter(
            build_id__in=build_status_map.keys()
        )

        updated_records = []
        for build_status in build_statuses_by_hardware:
            status = build_status_map[build_status.build_id]

            build_status.build_pass = 1 if status == "PASS" else 0
            build_status.build_failed = 1 if status == "FAIL" else 0
            build_status.build_inc = 1 if status not in ("PASS", "FAIL") else 0

            updated_records.append(build_status)

        if updated_records:
            BuildStatusByHardware.objects.bulk_update(
                updated_records,
                ["build_pass", "build_failed", "build_inc"],
                batch_size=INGEST_BATCH_SIZE,
            )


def aggregate_tests_status(tests_instances: list[Tests]) -> None:
    tests_filtered = (
        t
        for t in tests_instances
        if t.environment_misc and t.environment_misc.get("platform")
    )
    tests_to_insert = list(convert_test(t) for t in tests_filtered)

    test_ids_to_insert = [t.test_id for t in tests_to_insert]
    existing_test_ids = set(
        NewTest.objects.filter(test_id__in=test_ids_to_insert).values_list(
            "test_id", flat=True
        )
    )

    new_tests_only = [t for t in tests_to_insert if t.test_id not in existing_test_ids]

    NewTest.objects.bulk_create(
        tests_to_insert,
        batch_size=INGEST_BATCH_SIZE,
        ignore_conflicts=True,
    )

    build_status_by_hardware = prepare_build_status_by_hardware(new_tests_only)
    BuildStatusByHardware.objects.bulk_create(
        build_status_by_hardware,
        batch_size=INGEST_BATCH_SIZE,
        ignore_conflicts=True,
    )

    aggregated_data = aggregate_hardware_status_data(new_tests_only)

    with connection.cursor() as cursor:
        if aggregated_data:
            insert_query = """
                INSERT INTO hardware_status (
                    hardware_origin, hardware_platform, build_id, date, compatibles,
                    boot_pass, boot_failed, boot_inc,
                    test_pass, test_failed, test_inc
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (hardware_origin, hardware_platform, build_id, date)
                DO UPDATE SET
                    compatibles = COALESCE(hardware_status.compatibles, EXCLUDED.compatibles),
                    boot_pass = hardware_status.boot_pass + EXCLUDED.boot_pass,
                    boot_failed = hardware_status.boot_failed + EXCLUDED.boot_failed,
                    boot_inc = hardware_status.boot_inc + EXCLUDED.boot_inc,
                    test_pass = hardware_status.test_pass + EXCLUDED.test_pass,
                    test_failed = hardware_status.test_failed + EXCLUDED.test_failed,
                    test_inc = hardware_status.test_inc + EXCLUDED.test_inc
            """

            values = [
                (
                    data["hardware_origin"],
                    data["hardware_platform"],
                    data["build_id"],
                    data["date"],
                    data["compatibles"],
                    data["boot_pass"],
                    data["boot_failed"],
                    data["boot_inc"],
                    data["test_pass"],
                    data["test_failed"],
                    data["test_inc"],
                )
                for data in aggregated_data.values()
            ]

            cursor.executemany(insert_query, values)
