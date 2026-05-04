"""
Management command: migrate_sqlite_to_mysql

Reads all user data from the local SQLite database (slt/db.sqlite3) and
inserts it into the configured MySQL database using the Django ORM.

Tables migrated (in dependency order):
  1. user_account          → accounts.Account
  2. brain_quiz_attempt    → accounts.BrainQuizAttempt
  3. skeletal_sign_sample  → accounts.SkeletalSignSample
  4. syllabus_progress     → accounts.SyllabusProgress
  5. search_history        → accounts.SearchHistory

Usage:
    python manage.py migrate_sqlite_to_mysql
    python manage.py migrate_sqlite_to_mysql --sqlite-path /path/to/db.sqlite3
    python manage.py migrate_sqlite_to_mysql --dry-run
"""

import json
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import (
    Account,
    BrainQuizAttempt,
    SearchHistory,
    SkeletalSignSample,
    SyllabusProgress,
)


class Command(BaseCommand):
    help = (
        "Migrate all user data from the local SQLite database (db.sqlite3) "
        "into the configured MySQL database."
    )

    # ------------------------------------------------------------------ #
    # Argument definition                                                  #
    # ------------------------------------------------------------------ #

    def add_arguments(self, parser):
        parser.add_argument(
            "--sqlite-path",
            default=None,
            help=(
                "Absolute or relative path to the SQLite database file. "
                "Defaults to BASE_DIR/db.sqlite3."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help=(
                "Read from SQLite and report what would be migrated, "
                "but do not write anything to MySQL."
            ),
        )

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        sqlite_path = self._resolve_sqlite_path(options["sqlite_path"])
        dry_run = options["dry_run"]

        self.stdout.write(self.style.MIGRATE_HEADING("SQLite → MySQL migration"))
        self.stdout.write(f"  SQLite file : {sqlite_path}")
        self.stdout.write(
            f"  MySQL target: {settings.DATABASES['default']['HOST']}/"
            f"{settings.DATABASES['default']['NAME']}"
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("  Mode        : DRY RUN — no data will be written")
            )
        self.stdout.write("")

        conn = self._open_sqlite(sqlite_path)
        try:
            counts = self._migrate_all(conn, dry_run)
        finally:
            conn.close()

        self._print_summary(counts, dry_run)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _resolve_sqlite_path(self, cli_value: str | None) -> Path:
        if cli_value:
            path = Path(cli_value)
        else:
            path = Path(settings.BASE_DIR) / "db.sqlite3"

        if not path.exists():
            raise CommandError(
                f"SQLite database not found at '{path}'. "
                "Use --sqlite-path to specify the correct location."
            )
        return path.resolve()

    def _open_sqlite(self, path: Path) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as exc:
            raise CommandError(f"Cannot open SQLite database: {exc}") from exc

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cur.fetchone() is not None

    def _column_names(self, conn: sqlite3.Connection, table: str) -> list[str]:
        cur = conn.execute(f"PRAGMA table_info({table})")  # noqa: S608
        return [row["name"] for row in cur.fetchall()]

    # ------------------------------------------------------------------ #
    # Migration orchestration                                              #
    # ------------------------------------------------------------------ #

    def _migrate_all(
        self, conn: sqlite3.Connection, dry_run: bool
    ) -> dict[str, dict]:
        counts: dict[str, dict] = {}

        steps = [
            ("user_account", self._migrate_accounts),
            ("brain_quiz_attempt", self._migrate_brain_quiz_attempts),
            ("skeletal_sign_sample", self._migrate_skeletal_sign_samples),
            ("syllabus_progress", self._migrate_syllabus_progress),
            ("search_history", self._migrate_search_history),
        ]

        for table_name, migrate_fn in steps:
            self.stdout.write(f"  Migrating {table_name} …", ending="")
            self.stdout.flush()
            try:
                result = migrate_fn(conn, dry_run)
                counts[table_name] = result
                self.stdout.write(
                    f"\r  {self.style.SUCCESS('✔')} {table_name:<30} "
                    f"{result['migrated']:>6} migrated"
                    + (
                        f"  ({result['skipped']} skipped)"
                        if result.get("skipped")
                        else ""
                    )
                )
            except Exception as exc:  # noqa: BLE001
                counts[table_name] = {"migrated": 0, "skipped": 0, "error": str(exc)}
                self.stdout.write(
                    f"\r  {self.style.ERROR('✘')} {table_name:<30} ERROR: {exc}"
                )

        return counts

    # ------------------------------------------------------------------ #
    # Per-table migration methods                                          #
    # ------------------------------------------------------------------ #

    def _migrate_accounts(
        self, conn: sqlite3.Connection, dry_run: bool
    ) -> dict:
        """Migrate user_account → Account."""
        if not self._table_exists(conn, "user_account"):
            self.stdout.write(self.style.WARNING(" (table not found, skipping)"))
            return {"migrated": 0, "skipped": 0}

        columns = self._column_names(conn, "user_account")
        has_verification_token = "verification_token" in columns

        rows = conn.execute("SELECT * FROM user_account ORDER BY id").fetchall()
        migrated = skipped = 0

        if not dry_run:
            with transaction.atomic():
                for row in rows:
                    defaults = {
                        "real_name": row["real_name"],
                        "email": row["email"],
                        "password": row["password"],
                        "verification": bool(row["verification"]),
                        "date_created": row["date_created"],
                        "last_accessed": row["last_accessed"],
                    }
                    if has_verification_token:
                        defaults["verification_token"] = row["verification_token"]

                    _, created = Account.objects.update_or_create(
                        username=row["username"],
                        defaults=defaults,
                    )
                    if created:
                        migrated += 1
                    else:
                        skipped += 1
        else:
            migrated = len(rows)

        return {"migrated": migrated, "skipped": skipped}

    def _migrate_brain_quiz_attempts(
        self, conn: sqlite3.Connection, dry_run: bool
    ) -> dict:
        """Migrate brain_quiz_attempt → BrainQuizAttempt."""
        if not self._table_exists(conn, "brain_quiz_attempt"):
            return {"migrated": 0, "skipped": 0}

        rows = conn.execute(
            "SELECT * FROM brain_quiz_attempt ORDER BY id"
        ).fetchall()
        migrated = skipped = 0

        if not dry_run:
            # Build a username → Account cache to avoid N+1 queries.
            account_cache: dict[str, Account] = {
                a.username: a for a in Account.objects.all()
            }

            with transaction.atomic():
                for row in rows:
                    username_val = row["username"]
                    account = account_cache.get(username_val)
                    if account is None:
                        self.stderr.write(
                            self.style.WARNING(
                                f"    brain_quiz_attempt id={row['id']}: "
                                f"Account '{username_val}' not found in MySQL — skipping."
                            )
                        )
                        skipped += 1
                        continue

                    _, created = BrainQuizAttempt.objects.update_or_create(
                        username=account,
                        attempt_number=row["attempt_number"],
                        defaults={
                            "score": row["score"],
                            "date_attempt": row["date_attempt"],
                        },
                    )
                    if created:
                        migrated += 1
                    else:
                        skipped += 1
        else:
            migrated = len(rows)

        return {"migrated": migrated, "skipped": skipped}

    def _migrate_skeletal_sign_samples(
        self, conn: sqlite3.Connection, dry_run: bool
    ) -> dict:
        """Migrate skeletal_sign_sample → SkeletalSignSample.

        image_png is stored as a BLOB in SQLite; feature_vector is stored as
        JSON text.  Both are preserved verbatim.
        """
        if not self._table_exists(conn, "skeletal_sign_sample"):
            return {"migrated": 0, "skipped": 0}

        rows = conn.execute(
            "SELECT * FROM skeletal_sign_sample ORDER BY id"
        ).fetchall()
        migrated = skipped = 0

        if not dry_run:
            # Fetch existing PKs to avoid duplicates (no natural unique key).
            existing_ids: set[int] = set(
                SkeletalSignSample.objects.values_list("id", flat=True)
            )

            with transaction.atomic():
                for row in rows:
                    if row["id"] in existing_ids:
                        skipped += 1
                        continue

                    # feature_vector may already be a dict (sqlite3 JSON1) or
                    # a raw JSON string depending on the SQLite build.
                    feature_vector = row["feature_vector"]
                    if isinstance(feature_vector, str):
                        try:
                            feature_vector = json.loads(feature_vector)
                        except json.JSONDecodeError as exc:
                            self.stderr.write(
                                self.style.WARNING(
                                    f"    skeletal_sign_sample id={row['id']}: "
                                    f"invalid feature_vector JSON — {exc}. Storing as-is."
                                )
                            )

                    sample = SkeletalSignSample(
                        id=row["id"],
                        sign_name=row["sign_name"],
                        sign_folder=row["sign_folder"],
                        filename=row["filename"] or "",
                        image_png=bytes(row["image_png"]),
                        feature_vector=feature_vector,
                        source=row["source"],
                        captured_at=row["captured_at"],
                    )
                    sample.save()
                    migrated += 1
        else:
            migrated = len(rows)

        return {"migrated": migrated, "skipped": skipped}

    def _migrate_syllabus_progress(
        self, conn: sqlite3.Connection, dry_run: bool
    ) -> dict:
        """Migrate syllabus_progress → SyllabusProgress."""
        if not self._table_exists(conn, "syllabus_progress"):
            return {"migrated": 0, "skipped": 0}

        rows = conn.execute(
            "SELECT * FROM syllabus_progress ORDER BY id"
        ).fetchall()
        migrated = skipped = 0

        if not dry_run:
            account_cache: dict[int, Account] = {
                a.id: a for a in Account.objects.all()
            }

            with transaction.atomic():
                for row in rows:
                    account_id = row["account_id"]
                    account = account_cache.get(account_id)
                    if account is None:
                        self.stderr.write(
                            self.style.WARNING(
                                f"    syllabus_progress id={row['id']}: "
                                f"Account id={account_id} not found in MySQL — skipping."
                            )
                        )
                        skipped += 1
                        continue

                    _, created = SyllabusProgress.objects.update_or_create(
                        account=account,
                        syllabus_key=row["syllabus_key"],
                        defaults={
                            "current_term_index": row["current_term_index"],
                            "current_term": row["current_term"],
                            "total_terms": row["total_terms"],
                            "updated_at": row["updated_at"],
                        },
                    )
                    if created:
                        migrated += 1
                    else:
                        skipped += 1
        else:
            migrated = len(rows)

        return {"migrated": migrated, "skipped": skipped}

    def _migrate_search_history(
        self, conn: sqlite3.Connection, dry_run: bool
    ) -> dict:
        """Migrate search_history → SearchHistory."""
        if not self._table_exists(conn, "search_history"):
            return {"migrated": 0, "skipped": 0}

        rows = conn.execute(
            "SELECT * FROM search_history ORDER BY id"
        ).fetchall()
        migrated = skipped = 0

        if not dry_run:
            account_cache: dict[int, Account] = {
                a.id: a for a in Account.objects.all()
            }
            existing_ids: set[int] = set(
                SearchHistory.objects.values_list("id", flat=True)
            )

            with transaction.atomic():
                for row in rows:
                    if row["id"] in existing_ids:
                        skipped += 1
                        continue

                    account_id = row["account_id"]
                    account = account_cache.get(account_id)
                    if account is None:
                        self.stderr.write(
                            self.style.WARNING(
                                f"    search_history id={row['id']}: "
                                f"Account id={account_id} not found in MySQL — skipping."
                            )
                        )
                        skipped += 1
                        continue

                    SearchHistory.objects.create(
                        id=row["id"],
                        account=account,
                        search_term=row["search_term"],
                        searched_at=row["searched_at"],
                    )
                    migrated += 1
        else:
            migrated = len(rows)

        return {"migrated": migrated, "skipped": skipped}

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #

    def _print_summary(self, counts: dict[str, dict], dry_run: bool) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Summary"))

        total_migrated = 0
        total_skipped = 0
        has_errors = False

        for table, result in counts.items():
            migrated = result.get("migrated", 0)
            skipped = result.get("skipped", 0)
            error = result.get("error")
            total_migrated += migrated
            total_skipped += skipped
            if error:
                has_errors = True

        self.stdout.write(
            f"  Tables processed : {len(counts)}"
        )
        self.stdout.write(
            f"  Records migrated : {self.style.SUCCESS(str(total_migrated))}"
        )
        if total_skipped:
            self.stdout.write(
                f"  Records skipped  : {self.style.WARNING(str(total_skipped))} "
                "(already present or orphaned FK)"
            )
        if has_errors:
            self.stdout.write(
                self.style.ERROR(
                    "  One or more tables encountered errors — review output above."
                )
            )

        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run complete. Re-run without --dry-run to apply changes."
                )
            )
        elif not has_errors:
            self.stdout.write(
                self.style.SUCCESS("Migration complete. All data written to MySQL.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Migration finished with errors. Some records may not have been migrated."
                )
            )
