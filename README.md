# AI Hardware Atlas

Cipher Lacuna ("Decoding the gaps in AI knowledge"): public NVIDIA / AMD comparison, AI news and UAE AI, as one static bilingual page, plus a one-page PDF and an official-source checker. AI Hardware Atlas is the name of the hardware area.

## Current scope

- Three-pillar hub. `#home` is a short hero plus three equal pillars (Hardware, AI news, UAE AI), each a mini-dashboard with stats computed from the data and an "Open …" button. Inner views: `#hardware` (the full tool below), `#news`, `#uae` and `#contact`, each with a top nav, breadcrumb and "Back to overview". Unknown hashes open `#home`. Deep links such as `#hardware/level/Personal`, `#hardware/p/<id>`, `#news/uae` or `#uae/f/<id>` are applied and then reduced to the view. Filters stay in the query string next to the hash, so Copy link shares both. Without JavaScript all views render one after another.
- Featured products and the two UAE highlights on `#home` are chosen in `data/site.json` (unknown ids are skipped and filled from the data).
- Brand: Cipher Lacuna, with the owner's logo (`web/brand/logo.svg`) before the wordmark and the tagline under it in English or Arabic (the name stays Latin). Logo and favicon are sanitised and embedded as images, so they cannot run script; the PNG icons and the 1200 x 630 share preview (`web/brand/og.png`, made by `python scripts/make_og.py`) are copied to `dist/brand/`. Open Graph and X card tags point to https://buafra.github.io/ai-hardware-atlas/. See `web/brand/README.md`.
- GPU, system and rack entries, kept in `data/catalog.json`.
- Search and filters; numeric memory, bandwidth, power and launch-price sorting; chronological date-window sorting.
- Separate announcement and availability/target dates; memory scope on every entry.
- Specs where officially published: memory bandwidth, headline AI compute (precision and sparsity as stated), interconnect, form factor, cooling and launch MSRP. Unknown values show "Not listed".
- Three views: cards, a sortable table and a timeline of announcement vs availability.
- Side-by-side comparison of up to 4 products.
- "What can it run?" estimator: model size x precision + "extra memory for chat length and software" (default 20%, `extra` in the URL), with fit badges and a fits-only filter.
- Shareable links: search, filters, sort, view, comparison, estimator and language are kept in the URL.
- English / Arabic (RTL) interface, light / dark / auto theme, printable table.
- Official product photos (NVIDIA / AMD, credited and linked), stored as small WebP files in `images/` (`python scripts/images.py`).
- Approximate current prices in USD and AED: dated retail listings or reported estimates, with sources (`price` in the catalog). Without a UAE listing, AED is converted at the 3.6725 peg and labelled. The review issue flags prices older than 45 days.
- AI news in English and Arabic (full lists grouped by day in UAE time, Global / UAE filter), refreshed with every scheduled run from 40 vetted feeds (`data/news-sources.json`, `scripts/news.py`; the source list itself is not shown on the page). Each headline card shows the headline as text, a short summary, then a small "Source: <publisher> ↗" link to the original article and the date. Stored per item: headline, link, source, date and an excerpt of the publisher's own description (at most 280 characters, publisher boilerplate, wire datelines and invisible characters removed, never cut after an abbreviation or inside a quotation, labelled "From the publisher"). The excerpt comes from the feed or, when the feed only repeats the headline or gives nothing, from the description in the article page's own `<meta>` tags. Links and page reads must stay on the publisher's domains (redirects are checked before they are followed) and page reads respect the site's robots.txt. Per-source settings in `news-sources.json`: `feed_excerpt`, `excerpt_full_sentences`, `prefer_ai_summary`, `drop_titles`, `read_pages` (see the top of `scripts/news.py`).
- With `ANTHROPIC_API_KEY` (a repository secret; not set locally, and the tests mock the SDK): recent English headlines get an Arabic translation, marked "ترجمة آلية", and up to 30 items per run (headlines with no useful excerpt first, UAE first) get a 2–3 sentence summary in English and Arabic (`claude-opus-5`, structured output, 5 items per request), written from the article page when it can be read on the publisher's own domain (15 s, 1.5 MB, 6,000 characters of paragraph text) or else from the headline and excerpt. Summaries are labelled "AI summary" / «ملخص بالذكاء الاصطناعي», kept across runs, and API errors skip a batch without failing the run. What the AI steps did, or why they did nothing (no key, API errors, refusals), is recorded in `data/news.json` under `ai` (not shown on the site). The English page shows the English summary or an English excerpt; the Arabic page shows the Arabic summary or an Arabic excerpt.
- UAE AI section (marked with the UAE flag, never mirrored in Arabic): sourced fact cards (`data/uae.json`, reviewed by hand) plus headlines about the UAE or from UAE newsrooms.
- "Follow Qahwa & AI · @qahwa.w.ai" button (Instagram) in every view, the footer and the top bar (icon only on phones).
- Contact view: the email address (assembled by JavaScript, so it is not in the page source) and the follow button; there is no form.
- "Pick a model" in the estimator: every model listed on OpenRouter (`data/models.json`, refreshed with each scheduled run by `scripts/models.py`). Open-weight sizes come from Hugging Face safetensors metadata (all experts of MoE models counted); only unambiguous dense names are used as a fallback. Closed models are shown as cloud-only.
- Embedded fonts and one-page A3 PDF, generated from the same catalog.
- Scheduled workflow: 07:15 and 19:15 Dubai time (03:15 and 15:15 UTC).

## Publish

1. Create a public repository called `ai-hardware-atlas` and push this directory to `main`.
2. Repository Settings > Pages > Source: GitHub Actions.
   Settings > Actions > General > Workflow permissions: enable **Allow GitHub Actions to create and approve pull requests** (for AI drafts).
   Optional: add an `ANTHROPIC_API_KEY` repository secret to turn on AI drafts.
3. Run **Update hardware and publish** under Actions (manual run also checks sources).
4. Confirm the deployment succeeds; use the URL reported by the deployment job.

No API key is needed for the current source checker. GitHub's scheduled jobs can be delayed. GitHub may disable scheduled workflows in an inactive public repository after 60 days; inspect Actions if checks stop.

## What updates automatically

The workflow fetches official NVIDIA / AMD pages, discovers relevant official headlines, stores check health, and regenerates the website and PDF. Narrow, product-title-checked parsers update explicitly labeled specification fields configured in `data/refresh-rules.json`. Missing, conflicting or blocked source responses preserve existing data.

Parsers exist for 19 products (`data/refresh-rules.json`); each was checked against the live official page. Pages that serve several variants only have the unambiguous fields configured.

When anything needs attention (a changed page, a failed parser, an applied change or a new draft), the workflow opens or comments on a single GitHub issue labelled `source-review`. Fetch errors alone do not open an issue.

**AI drafts (optional).** With an `ANTHROPIC_API_KEY` secret, up to 3 newly discovered official headlines per run are sent to Claude (`claude-opus-5`, structured output). A draft is kept only if every evidence quote appears verbatim on the official page, it is a new product, and dates are well formed. Drafts go to `data/drafts/` in an `ai-drafts` pull request; they never enter the catalog by themselves. After checking a draft against the source:

```bash
python scripts/draft.py --promote data/drafts/<id>.json
```

Availability is never promoted to “released” just because a target date passed.

The on-page source-check time means a fetch pass ran. The per-product content review date is separate. The original catalog was reviewed 23 September 2026, with targeted corrections on 26 September. Some broad release windows remain vendor targets.

## Run locally

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests
node tests/test-sort.cjs
python scripts/refresh.py
python scripts/build.py                 # add --standalone ../../AI_Hardware_Atlas_2026.html to refresh the offline copy
python -m http.server 8080 --directory dist
```

Open http://localhost:8080. `dist/index.html` is self-contained and can also be opened directly. Keep the generated PDF next to it for the download button.

Browser smoke test (not part of `unittest discover`; needs `pip install playwright` and `python -m playwright install chromium`): serve `dist` and run `python tests/e2e_smoke.py http://localhost:8080/`. It clicks through every view in English and Arabic at 375, 768 and 1280 px and checks console errors, horizontal scroll, deep links, filters and the no-JavaScript fallback.

## Data integrity

- One source of truth for website, CSV and PDF.
- Source URLs restricted to official HTTPS vendor domains, including redirects.
- No secrets in HTML or JSON.
- Source fetch failures never delete products or replace values with zero.
- A failed build never reaches the deploy job.
- Changes are committed for rollback; source reports are retained as workflow artifacts.
- Human-edited fields are not sent to or executed by a model.

## Sources / platform documentation

- https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Individual vendor references are stored with each product.

DejaVu font licensing is included in `fonts/LICENSE.txt`.
