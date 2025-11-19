from typing import Sequence


from django.db import connection
from kernelCI_app.models import (
    Builds,
    Checkouts,
    PendingTest,
    StatusChoices,
    SimplifiedStatusChoices,
    Tests,
)
from kernelCI_app.utils import is_boot


def simplify_status(status: StatusChoices) -> SimplifiedStatusChoices:
    if status == StatusChoices.PASS:
        return SimplifiedStatusChoices.PASS
    elif status == StatusChoices.FAIL:
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


def aggregate_all(
    tests_instances: Sequence[Tests],
) -> None:
    pending_tests = (
        convert_test(test)
        for test in tests_instances
        if test.environment_misc and test.environment_misc.get("platform") is not None
    )

    if pending_tests:
        pending_tests_inserted = PendingTest.objects.bulk_create(
            pending_tests,
            ignore_conflicts=True,
        )
        print(f"inserted {len(pending_tests_inserted)} pending tests")


def run_all_aggregations(
    checkouts_instances: Sequence[Checkouts],
    tests_instances: Sequence[Tests],
) -> None:
    aggregate_checkouts(checkouts_instances)
    aggregate_all(tests_instances)
