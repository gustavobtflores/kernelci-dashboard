import time
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from kernelCI_app.models import (
    Builds,
    Checkouts,
    PendingBuild,
    PendingTest,
    Tests,
)
from kernelCI_app.management.commands.helpers.aggregation_helpers import (
    aggregate_hardware_status,
)


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
                        time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("Stopping pending aggregation processor...")
        else:
            self.process_pending_batch(batch_size)

    def process_pending_batch(self, batch_size: int) -> int:
        offset = 0
        while True:
            self.stdout.write(
                f"[DEBUG] Starting batch processing (offset={offset}, batch_size={batch_size})..."
            )

            pending_tests_batch = list(
                PendingTest.objects.all()[offset : offset + batch_size]
            )
            self.stdout.write(
                f"[DEBUG] Fetched {len(pending_tests_batch)} pending tests from database"
            )

            if not pending_tests_batch:
                self.stdout.write("[DEBUG] No pending tests found, exiting batch")
                return 0

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
                offset += batch_size
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
                offset += batch_size
                continue

            return self._process_ready_tests(
                ready_test_ids, ready_builds, ready_checkouts
            )

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
            hardware_status_data, _, _ = aggregate_hardware_status(
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
            else:
                self.stdout.write(
                    self.style.WARNING("[DEBUG] No hardware status data to insert")
                )

            self.stdout.write(
                f"[DEBUG] Deleting {len(ready_test_ids)} processed PendingTest entries..."
            )
            count = PendingTest.objects.filter(test_id__in=ready_test_ids).delete()[0]
            self.stdout.write(f"[DEBUG] Deleted {count} PendingTest entries")

            resolved_build_ids = [b.id for b in ready_builds.values()]
            if resolved_build_ids:
                self.stdout.write(
                    f"[DEBUG] Deleting {len(resolved_build_ids)} resolved PendingBuild entries..."
                )
                deleted_builds = PendingBuild.objects.filter(
                    build_id__in=resolved_build_ids
                ).delete()[0]
                self.stdout.write(
                    f"[DEBUG] Deleted {deleted_builds} PendingBuild entries"
                )
            else:
                self.stdout.write("[DEBUG] No PendingBuild entries to delete")

        self.stdout.write(
            self.style.SUCCESS(f"✓ Successfully aggregated {count} pending tests")
        )
        return count
