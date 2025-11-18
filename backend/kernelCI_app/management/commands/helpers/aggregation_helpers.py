from typing import Any, Sequence


from django.db import connection
from kernelCI_app.constants.general import MAESTRO_DUMMY_BUILD_PREFIX
from kernelCI_app.constants.ingester import INGEST_BATCH_SIZE
from kernelCI_app.models import (
    Builds,
    Checkouts,
    PendingBuild,
    PendingTest,
    Tests,
)
from kernelCI_app.utils import is_boot


def convert_test(t: Tests) -> PendingTest:
    return PendingTest(
        test_id=t.id,
        origin=t.origin,
        platform=t.environment_misc.get("platform"),
        compatible=t.environment_compatible,
        build_id=t.build_id,
        status=t.status,
        is_boot=is_boot(t.path) if t.path else False,
    )


def convert_build(b: Builds) -> PendingBuild:
    return PendingBuild(
        build_id=b.id,
        checkout_id=b.checkout_id,
        status=b.status,
    )


def aggregate_checkouts(checkouts_instances: Sequence[Checkouts]) -> None:
    values = [
        (
            checkout.id,
            checkout.origin,
            checkout.tree_name,
            checkout.git_repository_url,
            checkout.git_repository_branch,
            checkout.start_time,
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


def process_builds_by_checkout(
    builds: Sequence[Builds], checkouts: dict[str, Checkouts]
) -> tuple[dict[str, Builds], dict[str, list[Builds]], list[PendingBuild]]:
    builds_by_id = {}
    builds_by_checkout_id = {}
    pending_builds = []

    for build in builds:
        checkout_id = build.checkout_id

        if build.id.startswith(MAESTRO_DUMMY_BUILD_PREFIX):
            continue

        if checkout_id not in checkouts:
            pending_builds.append(convert_build(build))
            continue

        if checkout_id not in builds_by_checkout_id:
            builds_by_checkout_id[checkout_id] = []

        builds_by_id[build.id] = build
        builds_by_checkout_id[checkout_id].append(build)

    return builds_by_id, builds_by_checkout_id, pending_builds


def process_tests_by_build(
    tests: Sequence[Tests], builds_by_id: dict[str, Builds]
) -> tuple[dict[str, list[Tests]], list[PendingTest]]:
    pending_tests = []
    tests_by_build_id = {}

    for test in tests:
        build_id = test.build_id

        if not (test.environment_misc and test.environment_misc.get("platform")):
            continue

        if build_id not in builds_by_id:
            pending_tests.append(convert_test(test))
            continue

        tests_by_build_id.setdefault(build_id, []).append(test)

    return tests_by_build_id, pending_tests


def calculate_status_count(status: str) -> tuple[int, int, int]:
    if status == "PASS":
        return (1, 0, 0)
    elif status == "FAIL":
        return (0, 1, 0)
    else:
        return (0, 0, 1)


def aggregate_hardware_status(
    checkouts_by_id: dict[str, Checkouts],
    builds_by_checkout_id: dict[str, list[Builds]],
    tests_by_build_id: dict[str, list[Tests]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    hardware_status_data = {}
    for checkout in checkouts_by_id.values():
        checkout_id = checkout.id
        checkout_origin = checkout.origin
        checkout_start_time = checkout.start_time

        related_builds = builds_by_checkout_id.get(checkout_id, [])

        for build in related_builds:
            related_tests = tests_by_build_id.get(build.id, [])
            build_hardware_keys = set()

            for test in related_tests:
                platform = test.environment_misc.get("platform")
                hw_key = (checkout_origin, platform, checkout_id)
                build_hardware_keys.add(hw_key)

                hardware_status_data.setdefault(
                    hw_key,
                    {
                        "checkout_id": checkout_id,
                        "origin": checkout_origin,
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
                    },
                )

                status_record = hardware_status_data[hw_key]

                test_pass, test_failed, test_inc = calculate_status_count(test.status)

                if is_boot(test.path):
                    status_record["boot_pass"] += test_pass
                    status_record["boot_failed"] += test_failed
                    status_record["boot_inc"] += test_inc
                else:
                    status_record["test_pass"] += test_pass
                    status_record["test_failed"] += test_failed
                    status_record["test_inc"] += test_inc

            build_pass, build_failed, build_inc = calculate_status_count(build.status)

            for key in build_hardware_keys:
                hardware_status_data[key]["build_pass"] += build_pass
                hardware_status_data[key]["build_failed"] += build_failed
                hardware_status_data[key]["build_inc"] += build_inc

    return hardware_status_data


def aggregate_all(
    checkouts_instances: Sequence[Checkouts],
    builds_instances: Sequence[Builds],
    tests_instances: Sequence[Tests],
) -> None:
    checkouts_by_id = {}
    for checkout in checkouts_instances:
        checkouts_by_id[checkout.id] = checkout

    builds_by_id, builds_by_checkout_id, pending_builds = process_builds_by_checkout(
        builds_instances, checkouts_by_id
    )

    tests_by_build_id, pending_tests = process_tests_by_build(
        tests_instances, builds_by_id
    )

    hardware_status_data = aggregate_hardware_status(
        checkouts_by_id, builds_by_checkout_id, tests_by_build_id
    )

    if pending_builds:
        pending_builds_inserted = PendingBuild.objects.bulk_create(
            pending_builds,
            batch_size=INGEST_BATCH_SIZE,
            ignore_conflicts=True,
        )
        print(f"inserted {len(pending_builds_inserted)} pending builds")

    if pending_tests:
        pending_tests_inserted = PendingTest.objects.bulk_create(
            pending_tests,
            batch_size=INGEST_BATCH_SIZE,
            ignore_conflicts=True,
        )
        print(f"inserted {len(pending_tests_inserted)} pending tests")

    if hardware_status_data:
        values = [
            (
                data["checkout_id"],
                data["origin"],
                data["platform"],
                data["compatibles"],
                data["start_time"],
                data["build_pass"],
                data["build_failed"],
                data["build_inc"],
                data["boot_pass"],
                data["boot_failed"],
                data["boot_inc"],
                data["test_pass"],
                data["test_failed"],
                data["test_inc"],
            )
            for data in hardware_status_data.values()
        ]

        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO hardware_status (
                    checkout_id, origin, platform, compatibles, start_time,
                    build_pass, build_failed, build_inc,
                    boot_pass, boot_failed, boot_inc,
                    test_pass, test_failed, test_inc
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (origin, platform, checkout_id) DO UPDATE SET
                build_pass = hardware_status.build_pass + EXCLUDED.build_pass,
                build_failed = hardware_status.build_failed + EXCLUDED.build_failed,
                build_inc = hardware_status.build_inc + EXCLUDED.build_inc,
                boot_pass = hardware_status.boot_pass + EXCLUDED.boot_pass,
                boot_failed = hardware_status.boot_failed + EXCLUDED.boot_failed,
                boot_inc = hardware_status.boot_inc + EXCLUDED.boot_inc,
                test_pass = hardware_status.test_pass + EXCLUDED.test_pass,
                test_failed = hardware_status.test_failed + EXCLUDED.test_failed,
                test_inc = hardware_status.test_inc + EXCLUDED.test_inc
                """,
                values,
            )


def run_all_aggregations(
    checkouts_instances: Sequence[Checkouts],
    builds_instances: Sequence[Builds],
    tests_instances: Sequence[Tests],
) -> None:
    aggregate_checkouts(checkouts_instances)
    aggregate_all(checkouts_instances, builds_instances, tests_instances)
