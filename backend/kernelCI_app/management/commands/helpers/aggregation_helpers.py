from datetime import datetime


from django.db import connection
from kernelCI_app.constants.general import MAESTRO_DUMMY_BUILD_PREFIX
from kernelCI_app.constants.ingester import INGEST_BATCH_SIZE
from kernelCI_app.models import (
    Builds,
    Checkouts,
    HardwareStatus,
    PendingBuild,
    PendingTest,
    Tests,
)
from kernelCI_app.utils import is_boot

separated_statuses = ("PASS", "FAIL")


def date_to_timestamp(dt_input: str) -> int:
    return int(datetime.fromisoformat(dt_input).timestamp())


def convert_test(t: Tests) -> PendingTest:
    return PendingTest(
        id=t.id,
        origin=t.origin,
        platform=t.environment_misc.get("platform"),
        compatible=t.environment_compatible,
        build_id=t.build_id,
        status=t.status,
    )


def convert_build(b: Builds) -> PendingBuild:
    return PendingBuild(
        id=b.id,
        checkout_id=b.checkout_id,
        status=b.status,
    )


def aggregate_checkouts(checkouts_instances: list[Checkouts]) -> None:
    values = [
        (
            checkout.id,
            checkout.origin,
            checkout.tree_name,
            checkout.git_repository_url,
            checkout.git_repository_branch,
            date_to_timestamp(checkout.start_time),
        )
        for checkout in checkouts_instances
    ]

    modified_checkout_ids = []
    with connection.cursor() as cursor:
        for value_tuple in values:
            cursor.execute(
                """
                INSERT INTO latest_checkout (
                    checkout_id, origin, tree_name,
                    git_repository_url, git_repository_branch, start_time
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (origin, tree_name, git_repository_url, git_repository_branch)
                DO UPDATE SET
                    start_time = EXCLUDED.start_time,
                    checkout_id = EXCLUDED.checkout_id
                WHERE latest_checkout.start_time < EXCLUDED.start_time
                RETURNING checkout_id
                """,
                value_tuple,
            )
            result = cursor.fetchone()
            if result:
                modified_checkout_ids.append(result[0])

    print(
        f"executed {len(values)} rows, "
        f"modified {len(modified_checkout_ids)} checkout IDs: {modified_checkout_ids}"
    )


def aggregate_builds_status(builds_instances: list[Builds]) -> None:
    builds_to_insert = [
        convert_build(b)
        for b in builds_instances
        if not b.id.startswith(MAESTRO_DUMMY_BUILD_PREFIX)
    ]

    if not builds_to_insert:
        return

    created_builds = PendingBuild.objects.bulk_create(
        builds_to_insert,
        batch_size=INGEST_BATCH_SIZE,
        ignore_conflicts=True,
    )

    print(f"inserted {len(created_builds)} pending builds")


def aggregate_tests_status(tests_instances: list[Tests]) -> None:
    tests_to_insert = [
        convert_test(t)
        for t in tests_instances
        if t.environment_misc and t.environment_misc.get("platform")
    ]

    if not tests_to_insert:
        return

    created_tests = PendingTest.objects.bulk_create(
        tests_to_insert,
        batch_size=INGEST_BATCH_SIZE,
        ignore_conflicts=True,
    )

    print(f"inserted {len(created_tests)} pending tests")


def aggregate_all(
    checkouts_instances: list[Checkouts],
    builds_instances: list[Builds],
    tests_instances: list[Tests],
) -> None:
    builds_filtered = [
        b for b in builds_instances if not b.id.startswith(MAESTRO_DUMMY_BUILD_PREFIX)
    ]
    tests_filtered = [
        t
        for t in tests_instances
        if t.environment_misc and t.environment_misc.get("platform")
    ]

    checkouts_by_id = {c.id: c for c in checkouts_instances}
    builds_by_id = {b.id: b for b in builds_filtered}
    builds_by_checkout_id = {}

    for build in builds_filtered:
        builds_by_checkout_id.setdefault(build.checkout_id, []).append(build)

    tests_by_build_id = {}
    for test in tests_filtered:
        tests_by_build_id.setdefault(test.build_id, []).append(test)

    pending_builds = []
    pending_tests = []

    hardware_status_data = {}

    for checkout in checkouts_instances:
        checkout_id = checkout.id
        checkout_start_time = date_to_timestamp(checkout.start_time)

        related_builds = builds_by_checkout_id.get(checkout_id, [])

        for build in related_builds:
            related_tests = tests_by_build_id.get(build.id, [])

            build_pass = 1 if build.status == "PASS" else 0
            build_failed = 1 if build.status == "FAIL" else 0
            build_inc = 1 if build.status not in separated_statuses else 0

            build_hardware_keys = set()

            for test in related_tests:
                platform = test.environment_misc.get("platform")
                origin = test.origin
                key = (checkout_id, origin, platform)
                build_hardware_keys.add(key)

                if key not in hardware_status_data:
                    hardware_status_data[key] = {
                        "checkout_id": checkout_id,
                        "origin": origin,
                        "platform": platform,
                        "compatibles": test.environment_compatible,
                        "start_time": checkout_start_time,
                        "build_pass": 0,
                        "build_failed": 0,
                        "build_inc": 0,
                        "boot_pass": 0,
                        "boot_failed": 0,
                        "boot_inc": 0,
                        "test_pass": 0,
                        "test_failed": 0,
                        "test_inc": 0,
                    }

                status_record = hardware_status_data[key]

                test_pass = 1 if test.status == "PASS" else 0
                test_failed = 1 if test.status == "FAIL" else 0
                test_inc = 1 if test.status not in separated_statuses else 0

                if is_boot(test.path):
                    status_record["boot_pass"] += test_pass
                    status_record["boot_failed"] += test_failed
                    status_record["boot_inc"] += test_inc
                else:
                    status_record["test_pass"] += test_pass
                    status_record["test_failed"] += test_failed
                    status_record["test_inc"] += test_inc

            for key in build_hardware_keys:
                status_record["build_pass"] += build_pass
                status_record["build_failed"] += build_failed
                status_record["build_inc"] += build_inc

    for build in builds_filtered:
        if build.checkout_id not in checkouts_by_id:
            pending_builds.append(convert_build(build))

    for test in tests_filtered:
        if test.build_id not in builds_by_id:
            pending_tests.append(convert_test(test))

    if pending_builds:
        PendingBuild.objects.bulk_create(
            pending_builds,
            batch_size=INGEST_BATCH_SIZE,
            ignore_conflicts=True,
        )
        print(f"inserted {len(pending_builds)} pending builds")

    if pending_tests:
        PendingTest.objects.bulk_create(
            pending_tests,
            batch_size=INGEST_BATCH_SIZE,
            ignore_conflicts=True,
        )
        print(f"inserted {len(pending_tests)} pending tests")

    if hardware_status_data:
        hardware_status_records = [
            HardwareStatus(**data) for data in hardware_status_data.values()
        ]
        HardwareStatus.objects.bulk_create(
            hardware_status_records,
            batch_size=INGEST_BATCH_SIZE,
            ignore_conflicts=True,
        )
        print(f"inserted {len(hardware_status_records)} hardware status records")


def run_all_aggregations(
    checkouts_instances: list[Checkouts],
    builds_instances: list[Builds],
    tests_instances: list[Tests],
) -> None:
    aggregate_checkouts(checkouts_instances)
    aggregate_all(checkouts_instances, builds_instances, tests_instances)
    # aggregate_builds_status(builds_instances)
    # aggregate_tests_status(tests_instances)
