import hashlib
import time
from typing import Sequence
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from kernelCI_app.constants.general import MAESTRO_DUMMY_BUILD_PREFIX
from kernelCI_app.models import (
    Builds,
    Checkouts,
    HardwareStatusEntityType,
    PendingTest,
    ProcessedHardwareStatus,
    Tests,
)
from kernelCI_app.utils import is_boot


def get_hardware_key(origin: str, platform: str, checkout_id: str) -> bytes:
    return hashlib.sha256(f"{origin}|{platform}|{checkout_id}".encode("utf-8")).digest()


def calculate_status_count(status: str) -> tuple[int, int, int]:
    if status == "PASS":
        return (1, 0, 0)
    elif status == "FAIL":
        return (0, 1, 0)
    else:
        return (0, 0, 1)


def _init_status_record(checkout, platform, compatibles=None):
    return {
        "checkout_id": checkout.id,
        "origin": checkout.origin,
        "platform": platform,
        "compatibles": compatibles,
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
    }


def aggregate_hardware_status(
    tests_instances: Sequence[PendingTest],
    builds_by_id: dict[str, Builds],
    checkouts_by_id: dict[str, Checkouts],
):
    hardware_status_data = {}
    new_processed_entries = []

    contexts = []
    keys_to_check = set()

    for test in tests_instances:
        try:
            platform = test.environment_misc["platform"]
        except (AttributeError, KeyError, TypeError):
            continue

        if not platform:
            continue

        build = builds_by_id.get(test.build_id)
        if not build:
            continue

        try:
            checkout = checkouts_by_id[build.checkout_id]
        except KeyError:
            continue

        h_key = get_hardware_key(checkout.origin, platform, checkout.id)

        contexts.append((test, build, checkout, platform, h_key))
        keys_to_check.add(h_key)

    if not contexts:
        return hardware_status_data, new_processed_entries

    existing_processed = set()
    existing_qs = ProcessedHardwareStatus.objects.filter(
        hardware_key__in=keys_to_check
    ).values_list("hardware_key", "entity_id", "entity_type")

    for row in existing_qs:
        existing_processed.add((bytes(row[0]), row[1], row[2]))

    processed_builds_in_batch = set()

    for test, build, checkout, platform, h_key in contexts:
        record_key = (checkout.origin, platform, checkout.id)

        if record_key not in hardware_status_data:
            hardware_status_data[record_key] = _init_status_record(
                checkout, platform, test.environment_compatible
            )

        status_record = hardware_status_data[record_key]

        if (
            h_key,
            test.id,
            HardwareStatusEntityType.TEST.value,
        ) not in existing_processed:
            t_pass, t_fail, t_inc = calculate_status_count(test.status)

            if is_boot(test.path):
                status_record["boot_pass"] += t_pass
                status_record["boot_failed"] += t_fail
                status_record["boot_inc"] += t_inc
            else:
                status_record["test_pass"] += t_pass
                status_record["test_failed"] += t_fail
                status_record["test_inc"] += t_inc

            new_processed_entries.append(
                ProcessedHardwareStatus(
                    hardware_key=h_key,
                    entity_id=test.id,
                    entity_type=HardwareStatusEntityType.TEST,
                )
            )

        if build.id.startswith(MAESTRO_DUMMY_BUILD_PREFIX):
            continue

        if (
            h_key,
            build.id,
            HardwareStatusEntityType.BUILD.value,
        ) in existing_processed:
            continue

        if (h_key, build.id) in processed_builds_in_batch:
            continue

        b_pass, b_fail, b_inc = calculate_status_count(build.status)
        status_record["build_pass"] += b_pass
        status_record["build_failed"] += b_fail
        status_record["build_inc"] += b_inc

        processed_builds_in_batch.add((h_key, build.id))
        new_processed_entries.append(
            ProcessedHardwareStatus(
                hardware_key=h_key,
                entity_id=build.id,
                entity_type=HardwareStatusEntityType.BUILD,
            )
        )

    return hardware_status_data, new_processed_entries


class Command(BaseCommand):
    help = "Process pending tests and builds for hardware status aggregation"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of pending items to process in one batch",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run continuously in a loop",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Sleep interval in seconds when running in loop mode",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        loop = options["loop"]
        interval = options["interval"]

        if loop:
            self.stdout.write(
                f"Starting pending aggregation processor (interval={interval}s)..."
            )
            try:
                while True:
                    processed_count = self.process_pending_batch(batch_size)
                    if processed_count == 0:
                        self.stdout.write(f"[DEBUG] Sleeping for {interval} seconds")
                        time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("Stopping pending aggregation processor...")
        else:
            self.process_pending_batch(batch_size)

    def process_pending_batch(self, batch_size: int) -> int:
        last_processed_id = None

        while True:
            self.stdout.write(
                f"[DEBUG] Starting batch processing (last_processed_id={last_processed_id}, batch_size={batch_size})..."
            )

            qs = PendingTest.objects.order_by("id")
            if last_processed_id:
                qs = qs.filter(id__gt=last_processed_id)

            pending_tests_batch = list(qs[:batch_size])

            self.stdout.write(
                f"[DEBUG] Fetched {len(pending_tests_batch)} pending tests from database"
            )

            if not pending_tests_batch:
                self.stdout.write("[DEBUG] No pending tests found, exiting batch")
                return 0

            last_processed_id = pending_tests_batch[-1].id

            pending_build_ids = {pt.build_id for pt in pending_tests_batch}
            self.stdout.write(
                f"[DEBUG] Extracted {len(pending_build_ids)} unique build IDs from pending tests"
            )

            found_builds = Builds.objects.in_bulk(list(pending_build_ids))
            self.stdout.write(
                f"[DEBUG] Found {len(found_builds)} builds in database (expected {len(pending_build_ids)})"
            )

            if not found_builds:
                self.stdout.write(
                    self.style.WARNING(
                        "[DEBUG] No builds found for pending tests, skipping batch"
                    )
                )
                continue

            required_checkout_ids = {b.checkout_id for b in found_builds.values()}
            self.stdout.write(
                f"[DEBUG] Extracted {len(required_checkout_ids)} unique checkout IDs from builds"
            )

            found_checkouts = Checkouts.objects.in_bulk(list(required_checkout_ids))
            self.stdout.write(
                f"[DEBUG] Found {len(found_checkouts)} checkouts in database (expected {len(required_checkout_ids)})"
            )

            ready_test_ids = []
            ready_builds = {}
            ready_checkouts = {}
            skipped_no_build = 0
            skipped_no_checkout = 0

            for pt in pending_tests_batch:
                last_processed_id = pt.id
                build = found_builds.get(pt.build_id)
                if not build:
                    skipped_no_build += 1
                    continue

                checkout = found_checkouts.get(build.checkout_id)
                if not checkout:
                    skipped_no_checkout += 1
                    continue

                ready_test_ids.append(pt.test_id)
                ready_builds[build.id] = build
                ready_checkouts[checkout.id] = checkout

            self.stdout.write(
                f"[DEBUG] Dependency resolution complete: "
                f"{len(ready_test_ids)} tests ready, "
                f"{skipped_no_build} skipped (no build), "
                f"{skipped_no_checkout} skipped (no checkout)"
            )

            if not ready_test_ids:
                self.stdout.write(
                    self.style.WARNING(
                        "[DEBUG] No tests with resolved dependencies, skipping batch"
                    )
                )
                continue

            self._process_ready_tests(ready_test_ids, ready_builds, ready_checkouts)

    def _process_ready_tests(
        self, ready_test_ids, ready_builds, ready_checkouts
    ) -> int:
        tests_instances = list(Tests.objects.filter(id__in=ready_test_ids))
        self.stdout.write(
            f"[DEBUG] Fetched {len(tests_instances)} test instances from database"
        )

        self.stdout.write("[DEBUG] Starting database transaction for aggregation...")

        with transaction.atomic():
            self.stdout.write("[DEBUG] Calling aggregate_hardware_status helper...")
            hardware_status_data, new_processed_entries = aggregate_hardware_status(
                tests_instances, ready_builds, ready_checkouts
            )
            self.stdout.write(
                f"[DEBUG] aggregate_hardware_status returned {len(hardware_status_data)} hardware status entries"
            )

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

                self.stdout.write(
                    f"[DEBUG] Prepared {len(values)} rows for hardware_status upsert"
                )

                with connection.cursor() as cursor:
                    self.stdout.write(
                        "[DEBUG] Executing bulk upsert to hardware_status table..."
                    )
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
                    self.stdout.write("[DEBUG] Bulk upsert completed successfully")

                if new_processed_entries:
                    self.stdout.write(
                        f"[DEBUG] Inserting {len(new_processed_entries)} new processed entries into processed_hardware_status table..."
                    )
                    ProcessedHardwareStatus.objects.bulk_create(
                        new_processed_entries,
                        ignore_conflicts=True,
                    )
                    self.stdout.write(
                        "[DEBUG] New processed entries inserted successfully"
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("[DEBUG] No hardware status data to insert")
                )

            self.stdout.write(
                f"[DEBUG] Deleting {len(ready_test_ids)} processed PendingTest entries..."
            )
            count = PendingTest.objects.filter(test_id__in=ready_test_ids).delete()[0]
            self.stdout.write(f"[DEBUG] Deleted {count} PendingTest entries")

        self.stdout.write(
            self.style.SUCCESS(f"✓ Successfully aggregated {count} pending tests")
        )
        return count
