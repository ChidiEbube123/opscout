from django.contrib import admin

from .models import Opportunity, SavedOpportunity, UserProfilePreference


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "category", "funding_status", "deadline", "is_active", "date_scraped")
    list_filter = ("category", "funding_status", "is_active")
    search_fields = ("title", "organization", "summary")
    readonly_fields = ("date_scraped", "last_seen_at", "normalized_url", "slug")
    date_hierarchy = "deadline"


@admin.register(SavedOpportunity)
class SavedOpportunityAdmin(admin.ModelAdmin):
    list_display = ("user", "opportunity", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("user__username", "opportunity__title")


@admin.register(UserProfilePreference)
class UserProfilePreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "preferred_regions", "email_digest_enabled")
