# Analytics access setup (GA4 + Search Console)

One-time setup so `scripts/analytics-report.py` can pull GA4 behaviour and Search Console search data.
The generated reports (`docs/analytics/<date>.{md,json}`) are gitignored — they may contain traffic and query data and are regenerable.

## 1. Enable the APIs

In a Google Cloud project you own (any project — it only meters API quota):

```bash
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable analyticsdata.googleapis.com searchconsole.googleapis.com
```

## 2. Grant the account access to the data

These are separate from GCP IAM — access is granted inside the Analytics and Search Console products:

- **GA4:** in Analytics Admin → Property Access Management, ensure your Google account has at least **Viewer** on the property behind measurement id `G-EVHD7VH89H`.
- **Search Console:** in [Search Console](https://search.google.com/search-console) confirm `ssudake.com` is a verified property and your account is an owner/full user.
  If it isn't verified yet, add it (DNS or the `[verification] google = "…"` param Congo supports in `params.toml`) and submit `https://ssudake.com/sitemap.xml` under Sitemaps.

## 3. Authenticate (ADC) with the right scopes

The default ADC login scope does **not** cover Analytics or Search Console, so request them explicitly — otherwise the Search Console call returns `403 insufficient authentication scopes`:

```bash
gcloud auth application-default login \
  --scopes=openid,email,\
https://www.googleapis.com/auth/analytics.readonly,\
https://www.googleapis.com/auth/webmasters.readonly

gcloud auth application-default set-quota-project <YOUR_PROJECT_ID>
```

Run this in your own terminal with `! gcloud auth application-default login …` (it opens a browser).

## 4. Point the script at your properties

Find the **numeric GA4 property id** in Analytics Admin → Property Settings (this is *not* the `G-XXXX` measurement id).

Either export the values, or drop them in a gitignored `.env.analytics` at the repo root (matched by the `.env*` rule):

```bash
# .env.analytics
GA4_PROPERTY_ID=123456789
GSC_SITE_URL=https://ssudake.com/      # or sc-domain:ssudake.com for a domain property
```

## 5. Run

```bash
.venv/bin/python scripts/analytics-report.py            # last 28 days
.venv/bin/python scripts/analytics-report.py --days 90
```

Writes `docs/analytics/<date>.md` (human) and `<date>.json` (the loop diffs this across runs).
If a source isn't configured the report notes it and still emits the other.

## Notes

- Search Console data lags ~3 days; the script ends its window there.
- Meaningful trends need weeks of data — early reports on a freshly-migrated site will be sparse.
- The reusable loop that turns these reports into prioritized edits lives at `.claude/skills/reachability-loop/`.
