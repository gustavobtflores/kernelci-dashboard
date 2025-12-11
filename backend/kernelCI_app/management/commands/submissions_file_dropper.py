import os
import random
import tarfile
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Drop submission files to incoming directory from time to time with a random amount"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=300,
            help="Interval in seconds between file drops",
        )
        parser.add_argument(
            "--submissions-dir",
            type=str,
            default=os.path.join(os.getcwd(), "submissions"),
            help="Directory where submission files will be dropped",
        )
        parser.add_argument(
            "--archive-file",
            type=str,
            default=os.path.join(os.getcwd(), "all_submissions.tgz"),
            help="Archive file containing submissions",
        )
        parser.add_argument(
            "--min-files",
            type=int,
            default=10,
            help="Minimum number of files to drop at once",
        )
        parser.add_argument(
            "--max-files",
            type=int,
            default=1000,
            help="Maximum number of files to drop at once",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        submissions_path = options["submissions_dir"]
        submissions_file = options["archive_file"]
        min_files = options["min_files"]
        max_files = options["max_files"]

        try:
            while True:
                amount_to_drop = random.randint(min_files, max_files)

                extracted_amount = 0
                with tarfile.open(submissions_file, "r:xz") as tar:
                    for member in tar.getmembers():
                        if member.isfile:
                            tar.extract(member, submissions_path)
                            extracted_amount += 1
                            if extracted_amount >= amount_to_drop:
                                break

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Dropped {extracted_amount} submission files successfully"
                    )
                )
                self.stdout.write(f"Sleeping for {interval} seconds")
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("File dropper stopped"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred: {e}"))
