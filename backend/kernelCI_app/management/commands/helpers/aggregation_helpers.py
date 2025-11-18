from typing import Sequence


from django.db import connection
from kernelCI_app.constants.general import MAESTRO_DUMMY_BUILD_PREFIX
from kernelCI_app.models import (
    Builds,
    Checkouts,
    PendingBuild,
    PendingTest,
    SimplifiedStatusChoices,
    Tests,
)
from kernelCI_app.utils import is_boot


def simplify_status(status: str) -> str:
    if status == "PASS":
        return SimplifiedStatusChoices.PASS
    elif status == "FAIL":
        return SimplifiedStatusChoices.FAIL
    else:
        return SimplifiedStatusChoices.INCOMPLETE


def convert_test(t: Tests) -> PendingTest:
    return PendingTest(
        test_id=t.id,
        origin=t.origin,
        platform=t.environment_misc.get("platform"),
        compatible=t.environment_compatible,
        build_id=t.build_id,
        status=(
            simplify_status(t.status)
            if t.status
            else SimplifiedStatusChoices.INCOMPLETE
        ),
        is_boot=is_boot(t.path) if t.path else False,
    )


def convert_build(b: Builds) -> PendingBuild:
    return PendingBuild(
        build_id=b.id,
        checkout_id=b.checkout_id,
        status=simplify_status(b.status),
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

    with connection.cursor() as cursor:
        cursor.executemany(
            f"""
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
            """,
            values,
        )


def fetch_missing_checkouts(
    missing_checkout_ids: set[str],
) -> dict[str, Checkouts]:
    db_checkouts = Checkouts.objects.filter(id__in=missing_checkout_ids)
    return {checkout.id: checkout for checkout in db_checkouts}


def fetch_missing_builds(
    missing_build_ids: set[str],
) -> dict[str, Builds]:
    db_builds = Builds.objects.filter(id__in=missing_build_ids)
    return {build.id: build for build in db_builds}


def calculate_status_count(status: str) -> tuple[int, int, int]:
    if status == "PASS":
        return (1, 0, 0)
    elif status == "FAIL":
        return (0, 1, 0)
    else:
        return (0, 0, 1)


def aggregate_hardware_status(
    tests_instances: Sequence[Tests],
    builds_by_id: dict[str, Builds],
    checkouts_by_id: dict[str, Checkouts],
):
    hardware_status_data = {}
    seen_builds = set()
    pending_tests = []
    pending_builds = []

    for test in tests_instances:
        if not (test.environment_misc and test.environment_misc.get("platform")):
            continue

        if test.build_id not in builds_by_id:
            pending_tests.append(convert_test(test))
            continue

        build = builds_by_id[test.build_id]

        if build.checkout_id not in checkouts_by_id:
            pending_tests.append(convert_test(test))
            pending_builds.append(convert_build(build))
            continue

        checkout = checkouts_by_id[build.checkout_id]

        key = (checkout.origin, test.environment_misc.get("platform"), checkout.id)

        test_pass, test_failed, test_inc = calculate_status_count(test.status)

        hardware_status_data.setdefault(
            key,
            {
                "checkout_id": checkout.id,
                "origin": checkout.origin,
                "platform": test.environment_misc.get("platform"),
                "compatibles": test.environment_compatible,
                "start_time": checkout.start_time,
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

        status_record = hardware_status_data[key]

        if is_boot(test.path):
            status_record["boot_pass"] += test_pass
            status_record["boot_failed"] += test_failed
            status_record["boot_inc"] += test_inc
        else:
            status_record["test_pass"] += test_pass
            status_record["test_failed"] += test_failed
            status_record["test_inc"] += test_inc

        if build.id.startswith(MAESTRO_DUMMY_BUILD_PREFIX):
            continue

        seen_builds.add((key, build.id))

    for key, build_id in seen_builds:
        build = builds_by_id[build_id]
        build_pass, build_failed, build_inc = calculate_status_count(build.status)
        status_record = hardware_status_data[key]
        status_record["build_pass"] += build_pass
        status_record["build_failed"] += build_failed
        status_record["build_inc"] += build_inc

    return hardware_status_data, pending_tests, pending_builds


def aggregate_all(
    checkouts_instances: Sequence[Checkouts],
    builds_instances: Sequence[Builds],
    tests_instances: Sequence[Tests],
) -> None:
    checkouts_by_id = {checkout.id: checkout for checkout in checkouts_instances}
    builds_by_id = {}

    missing_builds = {
        test.build_id for test in tests_instances if test.build_id not in builds_by_id
    }
    missing_checkouts = set()
    for build in builds_instances:
        if build.checkout_id not in checkouts_by_id:
            missing_checkouts.add(build.checkout_id)

        builds_by_id[build.id] = build

    fetched_builds = fetch_missing_builds(missing_builds)
    fetched_checkouts = fetch_missing_checkouts(missing_checkouts)

    builds_by_id.update(fetched_builds)
    checkouts_by_id.update(fetched_checkouts)

    hardware_status_data, pending_tests, pending_builds = aggregate_hardware_status(
        tests_instances, builds_by_id, checkouts_by_id
    )

    if pending_builds:
        pending_builds_inserted = PendingBuild.objects.bulk_create(
            pending_builds,
            ignore_conflicts=True,
        )
        print(f"inserted {len(pending_builds_inserted)} pending builds")

    if pending_tests:
        pending_tests_inserted = PendingTest.objects.bulk_create(
            pending_tests,
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
