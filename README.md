# AI Hardware Atlas

Cipher Lacuna ("Decoding the gaps in AI knowledge"): public NVIDIA / AMD comparison, AI news and UAE AI, as one static bilingual page, plus a one-page PDF and an official-source checker. AI Hardware Atlas is the name of the hardware area.

## Current scope

- Four-pillar hub. `#home` is a short hero plus four equal pillars (Hardware, AI news, UAE AI, Learn AI; two by two on wide screens, one column on phones and tablets), each a mini-dashboard with stats computed from the data and an "Open …" button. Inner views: `#hardware` (the full tool below), `#news`, `#uae` and `#contact`, each with a top nav, breadcrumb and "Back to overview". Unknown hashes open `#home`. Deep links such as `#hardware/level/Personal`, `#hardware/p/<id>`, `#news/uae` or `#uae/f/<id>` are applied and then reduced to the view. Filters stay in the query string next to the hash, so Copy link shares both. Without JavaScript all views render one after another.
- Featured products and the UAE highlight (one key fact) on `#home` are chosen in `data/site.json`: `featured_products` (three) and `uae_highlights` (only the first id is used). Unknown ids are skipped and gaps filled from the data.
- Brand: Cipher Lacuna, with the owner's logo (`web/brand/logo.svg`) before the wordmark and the tagline under it in English or Arabic (the name stays Latin). Logo and favicon are sanitised and embedded as images, so they cannot run script; the PNG icons and the 1200 x 630 share preview (`web/brand/og.png`, made by `python scripts/make_og.py`) are copied to `dist/brand/`. Open Graph and X card tags point to https://cipherlacuna.ae/. See `web/brand/README.md`.
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
- AI news in English and Arabic (full lists grouped by day in UAE time, Global / UAE filter), refreshed with every scheduled run from 34 vetted feeds (`data/news-sources.json`, `scripts/news.py`; the source list itself is not shown on the page). Each headline card shows the headline as text, the summary (in full in the AI news and UAE AI lists, about three lines on the overview), a small label saying who wrote it, then a small "Source: <publisher> ↗" link to the original article and the date. The "Updated <date> · twice a day" line appears once on the site, at the top of the AI news view. Stored per item: headline, link, source, date and an excerpt of the publisher's own description (at most 280 characters, publisher boilerplate, wire datelines and invisible characters removed, never cut after an abbreviation or inside a quotation, labelled "From the publisher"). The excerpt comes from the feed or, when the feed only repeats the headline or gives nothing, from the description in the article page's own `<meta>` tags. Links and page reads must stay on the publisher's domains (redirects are checked before they are followed) and page reads respect the site's robots.txt. Per-source settings in `news-sources.json`: `feed_excerpt`, `excerpt_full_sentences`, `prefer_ai_summary`, `drop_titles`, `read_pages` (see the top of `scripts/news.py`).
- With `ANTHROPIC_API_KEY` (a repository secret; not set locally, and the tests mock the SDK): recent English headlines get an Arabic translation (not those already judged not mainly about AI; the summary step runs first), marked «ترجمة بالذكاء الاصطناعي» ("AI translation"), and up to 80 items per run (headlines with no useful excerpt first, UAE first, newest first) get a summary of 3–5 sentences, about 80–120 words, in English and Arabic (what happened, who is involved, when and where, and why it matters, only as the text states it; `claude-opus-5`, structured output, 5 items per request, over-long answers trimmed to whole sentences at 1,000 characters) plus an `ai_focus` verdict. Items judged not mainly about AI (a weekend digest, a lifestyle piece that only lists AI) stay in `data/news.json` but are left out of every list; items without a verdict follow the keyword rule. Each summary records its `summary_version`; raising `SUMMARY_VERSION` in `scripts/news.py` has older summaries rewritten (they stay until the new one succeeds, and earlier failed tries don't count). Summaries are written from the article page when it can be read on the publisher's own domain (15 s, 1.5 MB, 6,000 characters of paragraph text) or else from the headline and excerpt. They are labelled "AI summary" / «ملخص بالذكاء الاصطناعي», kept across runs, and API errors skip a batch without failing the run. What the AI steps did, or why they did nothing (no key, API errors, refusals), is recorded in `data/news.json` under `ai` (not shown on the site). The English page shows the English summary or an English excerpt; the Arabic page shows the Arabic summary or an Arabic excerpt.
- Content policy for the UAE and the GCC states (Saudi Arabia, Qatar, Kuwait, Bahrain, Oman), approved by the owner and applied to the site and the Android app (`scripts/policy.py`). Nothing is shown that criticises or casts in a negative light these countries, their emirates and regions, rulers, ruling families, officials, governments, armed forces, national symbols or state-linked entities (P1); that covers them in a negative or controversial political frame such as human-rights, surveillance, espionage, conflict, sanctions or export-control disputes (P2); that could harm national unity, public order or relations between states, or offends Islam or any religion (P3); or that spreads rumours about officials or institutions (P4). When in doubt, the story is left out, never rewritten. How the news step applies it (`scripts/news.py`):
  - M1: a story that mentions the region (English or Arabic, any spelling the detector knows: places, nationalities, leaders, ruling families, state entities) is kept only from a regional outlet: the UAE newsrooms (`"region": "uae"`, including the Dubai Media Office) and the GCC outlets marked `"regional_outlet": true` (Sky News Arabia, Asharq Al-Awsat, Independent Arabia). Another official UAE/GCC source can be marked `"official_region": true`. Global vendor newsrooms (NVIDIA, AMD, OpenAI ...) are not official sources of the region.
  - M2: with `ANTHROPIC_API_KEY`, every item gets an AI verdict (`policy_ok`, `policy_version`, `policy_hash`) before it is shown; a changed headline, translation, excerpt or summary needs a new one. Contradictory answers count as a fail; a story the model refuses or cannot judge twice in a run is removed. Without a key, or when the API fails, stories that mention the region stay hidden (fail closed).
  - M4: the repository is public, so nothing unverified that could still fail is written to `data/news.json`: a regional story only with a passing verdict and, with the key set, a new story only once it has one. A failing story is removed entirely; `data/news-blocked.json` keeps only one-way hashes (of its canonical URL, and of its source and headline) for 60 days so it is not collected again, even with a tracking query. Logs, `news.json` and the review issue show counts only. With the `TG_BOT_TOKEN` and `TG_CHAT_ID` secrets set, titles and reasons go privately to the owner on Telegram.
  - M5: `scripts/learn.py` checks the fixed content (Learn AI, `data/uae.json`, `data/about.json` and the hardware notes in `data/catalog.json`) and the build stops if a text field pairs a UAE/GCC name with conflict, attack, sanctions, criticism, detention, surveillance or similar wording.
  Raise `POLICY_VERSION` in `scripts/policy.py` whenever the policy text changes: every story is checked again.
- About Cipher Lacuna: the owner-approved text lives in `data/about.json` (promise, two about paragraphs, the name story, the four areas, trust, the Qahwa & AI line; English and Arabic) and is used as written, never reworded. The build checks it (all keys, non-empty English and Arabic, the areas hardware, news, uae, learn in that order, no update-schedule wording) and stops before writing anything if it is wrong. The hero's promise comes from it, and so do the page's `description`, `og:description` and `twitter:description` ("Cipher Lacuna: " and the English promise, cut at a sentence boundary if it would pass 200 characters), and `#contact` shows it as an About section under the email card (deep link `#contact/about`, footer link "About"); `scripts/app_data.py` exports the same file for the Android app as `dist/app/about.json`.
- UAE AI section: the latest AI headlines about the UAE or from UAE newsrooms first, then the sourced key-fact cards (`data/uae.json`, reviewed by hand, each with its "as of" date). The view shows the first 8 UAE headlines, then a "Show more" button (like the AI news list), so the key facts stay close on a phone. The overview's UAE pillar likewise shows the latest UAE headlines, then one highlighted fact (`uae_highlights` in `data/site.json`).
- "Follow Qahwa & AI · @qahwa.w.ai" button (Instagram) in every view, the footer and the top bar (icon only on phones).
- Contact view: the email address (assembled by JavaScript, so it is not in the page source) and, in the About section below it, the follow button beside the Qahwa & AI line (one follow button in the view); there is no form.
- "Pick a model" in the estimator: every model listed on OpenRouter (`data/models.json`, refreshed with each scheduled run by `scripts/models.py`). Open-weight sizes come from Hugging Face safetensors metadata (all experts of MoE models counted); only unambiguous dense names are used as a fallback. Closed models are shown as cloud-only.
- Embedded fonts and one-page A3 PDF, generated from the same catalog.
- Scheduled workflow: 6 times a day, every 4 hours: 03:15, 07:15, 11:15, 15:15, 19:15 and 23:15 Dubai time (23:15, 03:15, 07:15, 11:15, 15:15 and 19:15 UTC).

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
python -m venv .venv                    # once; then use the project's own Python for everything below
.venv/Scripts/python -m pip install -r requirements.txt   # on macOS/Linux: .venv/bin/python
.venv/Scripts/python -m unittest discover -s tests
node tests/test-sort.cjs
.venv/Scripts/python scripts/refresh.py
.venv/Scripts/python scripts/build.py                 # add --standalone ../../AI_Hardware_Atlas_2026.html to refresh the offline copy
python -m http.server 8080 --directory dist
```

Open http://localhost:8080. `dist/index.html` is self-contained and can also be opened directly. Keep the generated PDF next to it for the download button.

Learn AI is a separate static page, `learn.html`, rendered by `scripts/learn.py` from `data/learn/concepts.json` and `data/learn/stacks.json` (validated first; a data error fails the build). `scripts/build.py` writes it into `dist/` beside `index.html`, and with `--standalone` also beside the offline copy, with its links back pointing to that file. The overview links to it from the header, the footer and its fourth pillar (counts and picks come from the same data; `load_all()` validates it before anything is written, so a data error leaves `dist/` as it was). When the overview is in Arabic its links to `learn.html` carry `?lang=ar`, so a shared Arabic link stays Arabic on the Learn page; the other way, while the Learn page shows a language other than the saved one (a `?lang=ar` visit saves nothing), its links back to the overview carry `?lang=`. Its browser test: `.venv/Scripts/python tests/e2e_learn.py http://localhost:8080/`.

App data: `scripts/app_data.py` (called by `scripts/build.py`) writes `dist/app/` for the Cipher Lacuna Android app: `catalog.json`, `news.json`, `uae.json`, `learn.json`, `models.json` and a `manifest.json` with each file's SHA-256. It is the public data the site already shows, chosen by the same rules (the news list is `news_items()`, summaries come from `summary_of()`, backend-only catalog fields stay out). The app ships a copy and refreshes it from `https://cipherlacuna.ae/app/`; its notification check reads `news.json`. Tests: `tests/test_app_data.py`.

Browser smoke test (not part of `unittest discover`; needs Playwright in the project's `.venv`: `.venv/Scripts/python -m pip install playwright` and `.venv/Scripts/python -m playwright install chromium`): serve `dist` and run `.venv/Scripts/python tests/e2e_smoke.py http://localhost:8080/`. Use the `.venv` Python for the unit tests too: a system `python` without `reportlab` fails four test modules on import. It clicks through every view in English and Arabic at 375, 768 and 1280 px and checks console errors, horizontal scroll, deep links, filters and the no-JavaScript fallback.

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
