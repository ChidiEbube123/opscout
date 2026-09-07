import hashlib
import urllib.parse

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


def normalize_url(url: str) -> str:
    """
    Normalize a URL so the same opportunity posted with tracking params,
    trailing slashes, or http/https differences doesn't create duplicates.
    """
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url.strip().lower())
    netloc = parsed.netloc.replace("www.", "")
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit(("https", netloc, path, "", ""))


class Category(models.TextChoices):
    MSC = "MSc", "MSc / Masters"
    PHD = "PhD", "PhD"
    QUANT = "Quant Role", "Quant Role"
    SWE = "SWE Role", "Software / Tech Role"
    HACKATHON = "Hackathon", "Hackathon"
    FELLOWSHIP = "Fellowship", "Fellowship"
    SCHOLARSHIP = "Scholarship", "Scholarship"
    OTHER = "Other", "Other"


class FundingType(models.TextChoices):
    FULLY_FUNDED = "Fully Funded", "Fully Funded"
    PARTIAL = "Partial", "Partially Funded"
    CASH_PRIZE = "Cash Prize", "Cash Prize"
    PAID_ROLE = "Paid Role", "Paid Role"
    UNFUNDED = "Unfunded", "Unfunded / Unknown"


class Opportunity(models.Model):
    """A single scouted opportunity (MSc program, quant role, hackathon, etc.)."""

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=350, unique=True, blank=True)
    organization = models.CharField(max_length=200, blank=True)
    url = models.URLField(max_length=600)
    normalized_url = models.CharField(max_length=600, db_index=True, blank=True)

    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    funding_status = models.CharField(
        max_length=30, choices=FundingType.choices, default=FundingType.UNFUNDED
    )

    summary = models.TextField(blank=True)
    eligibility_criteria = models.TextField(blank=True)

    deadline = models.DateField(null=True, blank=True, db_index=True)

    # Raw payload from Gemini for auditing / re-processing without another API call
    raw_json = models.JSONField(default=dict, blank=True)

    date_scraped = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["deadline", "-date_scraped"]
        constraints = [
            models.UniqueConstraint(fields=["normalized_url"], name="unique_normalized_url"),
        ]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["deadline", "is_active"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.organization})"

    def save(self, *args, **kwargs):
        self.normalized_url = normalize_url(self.url)
        if not self.slug:
            base_slug = slugify(self.title)[:250] or "opportunity"
            # Ensure slug uniqueness deterministically using a short hash of the URL
            url_hash = hashlib.sha1(self.normalized_url.encode()).hexdigest()[:8]
            self.slug = f"{base_slug}-{url_hash}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("opportunity_detail", kwargs={"slug": self.slug})

    @property
    def days_to_deadline(self):
        if not self.deadline:
            return None
        return (self.deadline - timezone.now().date()).days

    @property
    def is_urgent(self):
        """Deadline within 7 days -> highlight red in the UI."""
        days = self.days_to_deadline
        return days is not None and 0 <= days <= 7

    @property
    def is_expired(self):
        days = self.days_to_deadline
        return days is not None and days < 0


class UserProfilePreference(models.Model):
    """Per-user filters: what kinds of opportunities they care about."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scout_preference"
    )
    preferred_categories = models.JSONField(default=list, blank=True)
    preferred_regions = models.CharField(
        max_length=300,
        blank=True,
        help_text="Comma-separated regions of interest, e.g. Europe, UK, Canada, Remote",
    )
    keywords = models.CharField(
        max_length=300,
        blank=True,
        help_text="Extra keywords to prioritize, e.g. quant, fintech, machine learning",
    )
    email_digest_enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user}"


class SavedOpportunityStatus(models.TextChoices):
    NEW = "New", "New"
    INTERESTED = "Interested", "Interested"
    APPLIED = "Applied", "Applied"
    REJECTED = "Rejected", "Rejected"
    ACCEPTED = "Accepted", "Accepted"


class SavedOpportunity(models.Model):
    """A user's personal bookmark + tracked status for an Opportunity."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_opportunities"
    )
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.CASCADE, related_name="saves"
    )
    status = models.CharField(
        max_length=20, choices=SavedOpportunityStatus.choices, default=SavedOpportunityStatus.NEW
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "opportunity"], name="unique_user_saved_opportunity"),
        ]

    def __str__(self):
        return f"{self.user} -> {self.opportunity} [{self.status}]"
