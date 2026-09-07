"""
python manage.py run_scout

Free-tier friendly ingestion command. Intended to be triggered by:
- GitHub Actions cron (see .github/workflows/scheduled_scout.yml), or
- A manual run from the shell / Django admin action.

No Celery, no Redis, no long-running worker process required.
"""
import datetime
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from scout.models import Opportunity
from scout.services import gemini_scout

logger = logging.getLogger("scout")


class Command(BaseCommand):
    help = "Query Gemini (with Google Search grounding) for new opportunities and upsert them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lanes",
            nargs="*",
            default=None,
            help="Optional list of lane keys to run (default: all lanes). "
            "e.g. --lanes msc_europe quant_roles",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and validate results but do not write to the database.",
        )
        parser.add_argument(
            "--archive-stale",
            action="store_true",
            default=True,
            help="Deactivate opportunities whose deadline has passed.",
        )

    def handle(self, *args, **options):
        lane_keys = options.get("lanes")
        dry_run = options["dry_run"]

        self.stdout.write(self.style.NOTICE(f"Starting OpportunityScout run at {timezone.now().isoformat()}"))

        try:
            results = gemini_scout.run_all_lanes(lane_keys=lane_keys)
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        total_seen = 0
        total_created = 0
        total_updated = 0
        total_errors = 0

        for result in results:
            if result.error:
                total_errors += 1
                self.stderr.write(self.style.ERROR(f"[{result.lane_key}] ERROR: {result.error}"))
                continue

            self.stdout.write(f"[{result.lane_key}] {len(result.items)} valid item(s) parsed.")
            total_seen += len(result.items)

            if dry_run:
                for item in result.items:
                    self.stdout.write(f"  DRY-RUN would upsert: {item['title']} ({item['url']})")
                continue

            for item in result.items:
                created = self._upsert_opportunity(item)
                if created:
                    total_created += 1
                else:
                    total_updated += 1

        if not dry_run and options["archive_stale"]:
            archived = self._archive_expired()
            self.stdout.write(f"Archived {archived} expired opportunit(y/ies).")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Seen={total_seen} Created={total_created} Updated={total_updated} "
                f"LaneErrors={total_errors}"
            )
        )

    @transaction.atomic
    def _upsert_opportunity(self, item: dict) -> bool:
        """Insert or update an Opportunity keyed on its normalized URL. Returns True if created."""
        from scout.models import normalize_url

        deadline = None
        if item["deadline"]:
            try:
                deadline = datetime.date.fromisoformat(item["deadline"])
            except ValueError:
                deadline = None

        norm_url = normalize_url(item["url"])

        obj, created = Opportunity.objects.update_or_create(
            normalized_url=norm_url,
            defaults={
                "title": item["title"],
                "organization": item["organization"],
                "url": item["url"],
                "category": item["category"],
                "funding_status": item["funding_status"],
                "summary": item["summary"],
                "eligibility_criteria": item["eligibility_criteria"],
                "deadline": deadline,
                "raw_json": item,
                "is_active": True,
            },
        )
        action = "Created" if created else "Updated"
        logger.info("%s opportunity: %s", action, obj.title)
        return created

    def _archive_expired(self) -> int:
        today = timezone.now().date()
        qs = Opportunity.objects.filter(is_active=True, deadline__lt=today)
        count = qs.count()
        qs.update(is_active=False)
        return count
