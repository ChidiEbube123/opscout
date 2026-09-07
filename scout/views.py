from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import PreferenceForm, SignUpForm
from .models import (
    Category,
    Opportunity,
    SavedOpportunity,
    SavedOpportunityStatus,
    UserProfilePreference,
)

PAGE_SIZE = 24


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


def _filter_opportunities(request):
    """Shared query-building logic used by both the full dashboard and the HTMX partial."""
    qs = Opportunity.objects.filter(is_active=True)

    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(organization__icontains=query)
            | Q(summary__icontains=query)
        )

    category = request.GET.get("category", "").strip()
    if category and category != "All":
        qs = qs.filter(category=category)

    funding = request.GET.get("funding", "").strip()
    if funding and funding != "All":
        qs = qs.filter(funding_status=funding)

    sort = request.GET.get("sort", "deadline")
    sort_map = {
        "deadline": "deadline",
        "newest": "-date_scraped",
        "title": "title",
    }
    qs = qs.order_by(sort_map.get(sort, "deadline"))

    return qs


def dashboard_view(request):
    """Full page load: renders base + initial opportunity list."""
    qs = _filter_opportunities(request)[:PAGE_SIZE]

    saved_map = {}
    if request.user.is_authenticated:
        saved_map = {
            s.opportunity_id: s.status
            for s in SavedOpportunity.objects.filter(user=request.user)
        }

    context = {
        "opportunities": qs,
        "categories": Category.choices,
        "current_category": request.GET.get("category", "All"),
        "current_query": request.GET.get("q", ""),
        "current_sort": request.GET.get("sort", "deadline"),
        "saved_map": saved_map,
    }
    return render(request, "dashboard.html", context)


def opportunity_list_partial(request):
    """HTMX endpoint: returns just the <div id='opportunity-list'> partial for live search/filter/sort."""
    qs = _filter_opportunities(request)[:PAGE_SIZE]

    saved_map = {}
    if request.user.is_authenticated:
        saved_map = {
            s.opportunity_id: s.status
            for s in SavedOpportunity.objects.filter(user=request.user)
        }

    return render(
        request,
        "partials/opportunity_list.html",
        {"opportunities": qs, "saved_map": saved_map},
    )


def opportunity_detail_partial(request, slug):
    """HTMX endpoint: slide-over drawer with full opportunity details."""
    opportunity = get_object_or_404(Opportunity, slug=slug)
    current_status = None
    if request.user.is_authenticated:
        saved = SavedOpportunity.objects.filter(user=request.user, opportunity=opportunity).first()
        current_status = saved.status if saved else None
    return render(
        request,
        "partials/opportunity_detail.html",
        {"opportunity": opportunity, "current_status": current_status, "statuses": SavedOpportunityStatus.choices},
    )


@login_required
@require_POST
def toggle_save(request, slug):
    """
    HTMX endpoint: create/update a SavedOpportunity for the current user and
    return just the status-badge partial to swap inline (e.g. in a card or the drawer).
    """
    opportunity = get_object_or_404(Opportunity, slug=slug)
    new_status = request.POST.get("status", SavedOpportunityStatus.INTERESTED)
    valid_statuses = {choice.value for choice in SavedOpportunityStatus}
    if new_status not in valid_statuses:
        new_status = SavedOpportunityStatus.INTERESTED

    SavedOpportunity.objects.update_or_create(
        user=request.user,
        opportunity=opportunity,
        defaults={"status": new_status},
    )

    return render(
        request,
        "partials/status_badge.html",
        {"opportunity": opportunity, "current_status": new_status, "statuses": SavedOpportunityStatus.choices},
    )


@login_required
@require_POST
def unsave(request, slug):
    opportunity = get_object_or_404(Opportunity, slug=slug)
    SavedOpportunity.objects.filter(user=request.user, opportunity=opportunity).delete()
    return render(
        request,
        "partials/status_badge.html",
        {"opportunity": opportunity, "current_status": None, "statuses": SavedOpportunityStatus.choices},
    )


@login_required
def tracker_view(request):
    """Kanban-style tracker grouped by status."""
    saves = (
        SavedOpportunity.objects.filter(user=request.user)
        .select_related("opportunity")
        .order_by("opportunity__deadline")
    )
    columns = {choice.value: [] for choice in SavedOpportunityStatus}
    for s in saves:
        columns.setdefault(s.status, []).append(s)

    return render(
        request,
        "tracker.html",
        {"columns": columns, "statuses": SavedOpportunityStatus.choices},
    )


@login_required
def preferences_view(request):
    pref, _ = UserProfilePreference.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = PreferenceForm(request.POST, instance=pref)
        if form.is_valid():
            form.save()
            return redirect("dashboard")
    else:
        form = PreferenceForm(instance=pref)
    return render(request, "preferences.html", {"form": form})
