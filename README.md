# OpportunityScout

A Django + HTMX + Tailwind app that uses the **Gemini API** (with live Google
Search grounding) to scout real, currently-open opportunities — fully funded
MSc programs abroad, quant/tech roles with visa sponsorship, hackathons, and
fellowships — and gives you a searchable feed plus a personal Kanban tracker
for your applications.

Built to run at **$0/month**:

| Layer            | Service                          | Free tier used |
|------------------|-----------------------------------|----------------|
| App hosting      | Vercel (serverless Python/WSGI)  | Hobby plan |
| Database         | Supabase Postgres                | Free project |
| AI / discovery   | Gemini API (`gemini-2.5-flash`)  | Free tier |
| Scheduled scan   | GitHub Actions cron               | Public/private repo, free minutes |

No Celery, no Redis, no always-on worker. The daily scan is just
`python manage.py run_scout` triggered by a GitHub Actions cron job.

---

## 1. Project layout

```
opportunityscout/
├── manage.py
├── requirements.txt
├── vercel.json                 # Vercel routing config
├── build_files.sh              # Vercel build step (installs deps + collectstatic)
├── .env.example
├── api/
│   └── index.py                # Vercel serverless entrypoint (wraps Django WSGI)
├── config/
│   ├── settings.py             # Supabase Postgres + WhiteNoise + security settings
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── scout/                      # The core app
│   ├── models.py                # Opportunity, UserProfilePreference, SavedOpportunity
│   ├── views.py                 # Dashboard, HTMX partials, tracker, preferences
│   ├── urls.py
│   ├── urls_auth.py              # /accounts/signup/
│   ├── forms.py
│   ├── admin.py
│   ├── services/
│   │   └── gemini_scout.py      # Isolated Gemini API integration (search-grounded)
│   ├── management/commands/
│   │   └── run_scout.py         # `python manage.py run_scout`
│   ├── templatetags/
│   │   └── scout_extras.py      # Badge color helpers
│   └── migrations/
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── tracker.html
│   ├── preferences.html
│   ├── registration/{login,signup}.html
│   └── partials/
│       ├── opportunity_list.html
│       ├── opportunity_card.html
│       ├── opportunity_detail.html   # HTMX slide-over drawer
│       └── status_badge.html         # HTMX-swappable save/status control
└── .github/workflows/
    └── scheduled_scout.yml       # Free daily cron
```

---

## 2. Local setup

```bash
python -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in DATABASE_URL / GEMINI_API_KEY
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`. Without `DATABASE_URL` set, it falls back to
local SQLite automatically, so you can try the UI before wiring up Supabase.

To pull in real data immediately:

```bash
python manage.py run_scout --dry-run     # preview without writing to DB
python manage.py run_scout               # actually scout + upsert
python manage.py run_scout --lanes quant_roles msc_europe   # run specific lanes only
```

---

## 3. Set up Supabase (free Postgres)

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **Project Settings → Database → Connection string → URI**, and copy
   the **Connection pooling** string (port `6543`, uses `pgbouncer`) — this
   matters because Vercel's serverless functions open a fresh connection per
   invocation, and pooling avoids exhausting Supabase's connection limit.
3. Put that URI in `DATABASE_URL` (both in your local `.env` and later in
   Vercel + GitHub secrets).
4. Run migrations against it once:
   ```bash
   DATABASE_URL="postgresql://...supabase..." python manage.py migrate
   ```

---

## 4. Get a Gemini API key (free tier)

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and
   create a key.
2. Put it in `GEMINI_API_KEY`.
3. The free tier has daily/per-minute rate limits — `run_scout` calls Gemini
   once per "lane" (5 lanes by default: MSc-Europe, quant roles, SWE roles,
   hackathons, fellowships), which comfortably fits inside one daily cron run.
   Use `--lanes` to run a subset if you ever need to stay further under quota.

---

## 5. Deploy to Vercel (free)

1. Push this repo to GitHub.
2. In Vercel, **Add New Project** → import the repo. Vercel will detect
   `vercel.json` and use the Python builder pointed at `api/index.py`.
3. Add these Environment Variables in the Vercel project settings:
   - `DJANGO_SECRET_KEY` (generate a long random string)
   - `DJANGO_DEBUG=False`
   - `DJANGO_ALLOWED_HOSTS=.vercel.app,your-project.vercel.app`
   - `CSRF_TRUSTED_ORIGINS=https://*.vercel.app,https://your-project.vercel.app`
   - `DATABASE_URL` (Supabase pooled URI from step 3)
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL=gemini-2.5-flash`
4. Deploy. Vercel runs `build_files.sh` implicitly via the Python builder,
   which installs dependencies and runs `collectstatic`.
5. **Run migrations against production once** from your local machine (or
   Supabase's SQL editor) — Vercel's serverless functions don't run one-off
   management commands automatically:
   ```bash
   DATABASE_URL="<supabase-uri>" python manage.py migrate
   DATABASE_URL="<supabase-uri>" python manage.py createsuperuser
   ```

> Note: Vercel's Python runtime support for full Django apps is community/best-effort
> rather than official. If you hit friction, **Render** (free web service tier)
> or **Railway** work as drop-in alternatives — the codebase itself
> (WSGI app, settings, migrations) doesn't need to change, only the deploy
> config. Since Vercel's free web service tier can sleep/spin down and cold-start,
> also read Vercel's current docs on Python runtime limits before relying on it
> for anything you can't afford to have briefly unavailable.

---

## 6. Set up the free daily cron (GitHub Actions)

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
   and add:
   - `DJANGO_SECRET_KEY`
   - `DATABASE_URL` (same Supabase pooled URI)
   - `GEMINI_API_KEY`
2. The workflow at `.github/workflows/scheduled_scout.yml` runs every day at
   05:00 UTC, applies migrations, then runs `python manage.py run_scout`.
3. You can also trigger it manually any time from the **Actions** tab via
   "Run workflow" (this repo's workflow has `workflow_dispatch` enabled).

---

## 7. How the Gemini engine works (`scout/services/gemini_scout.py`)

- Calls `gemini-2.5-flash` via the `google-genai` SDK.
- Enables `tools=[Tool(google_search=GoogleSearch())]` so the model grounds
  its answers in live web results instead of memorized (possibly stale or
  hallucinated) information.
- Because grounding + strict `response_mime_type=application/json` isn't
  reliably combinable in every SDK/model combination, the module instead
  gives Gemini a very explicit "return only a JSON array" instruction and
  then defensively extracts/validates the JSON from the response text
  (`_extract_json` + `validate_item`), so malformed output never crashes the
  ingestion run — bad items are just dropped and logged.
- Search queries are split into 5 rotating "lanes" (see `SEARCH_LANES`) tuned
  specifically around: fully-funded MSc/PhD programs in Europe open to
  international/African applicants, quant developer/researcher roles with
  visa sponsorship, tech SWE roles with visa sponsorship, global hackathons,
  and fellowships open to applicants from Africa. Edit `SEARCH_LANES` in that
  file to tune targeting further (e.g. add "Canada", "Singapore", specific
  firms, etc.).
- `run_scout.py` deduplicates on a normalized URL (`Opportunity.normalized_url`,
  enforced with a `UniqueConstraint`), so re-running the scan daily updates
  existing rows via `update_or_create` instead of creating duplicates, and
  auto-archives (`is_active=False`) anything whose deadline has passed.

---

## 8. Key UX flows

- **Feed (`/`)**: live search + category/funding filters + sort, all via
  HTMX (`hx-get` on `#filter-form`, debounced, swapping `#opportunity-list`
  with no full page reload).
- **Detail drawer**: clicking a card title does `hx-get` into `#drawer`,
  rendering a slide-over panel with full summary + eligibility criteria.
- **Save / status tracker**: the badge/button under each card does
  `hx-post` to `toggle_save`, which does `update_or_create` on
  `SavedOpportunity` and returns just the badge partial (`hx-swap="outerHTML"`)
  — no page reload, and the same partial is reused in the card, the drawer,
  and the Kanban tracker so state always stays visually consistent.
- **Tracker (`/tracker/`)**: groups your `SavedOpportunity` rows into 5
  columns (New, Interested, Applied, Rejected, Accepted) — a lightweight
  Kanban view without any drag-and-drop JS framework.
- Deadlines within 7 days are highlighted in red (`Opportunity.is_urgent`)
  everywhere they're shown.

---

## 9. Suggested next steps

- Add an email digest (`UserProfilePreference.email_digest_enabled` is
  already modeled) using Supabase's built-in SMTP or a free Resend/Postmark
  tier, sent from the same GitHub Actions workflow after `run_scout`.
- Add a `--notify` flag to `run_scout` that pings a Slack/Discord webhook
  when new "Fully Funded" or urgent-deadline items are created — genuinely
  useful for not missing a deadline.
- If Gemini's free-tier rate limits become a constraint, cut `SEARCH_LANES`
  down or stagger lanes across multiple cron times a day instead of one.
