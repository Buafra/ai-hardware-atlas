# Brand: Cipher Lacuna

The site is branded **Cipher Lacuna**. The hardware area keeps its own name, **AI Hardware Atlas**. The brand name is always written in Latin letters, in English and in Arabic.

- Tagline (shown under the wordmark, switches with the language toggle; hidden below 1000 px inside a section, where the section name takes its line; at 480 px and below the header has no room for it, so the home hero shows it under the name instead):
  - EN: Decoding the gaps in AI knowledge
  - AR: كشف المجهول في عالم الذكاء الاصطناعي
- Palette: deep purple #42208D, violet #753ACA, magenta #D52F89, cyan #22D4D6; dark background #0E1222, light background #F5F8FF.

The artwork is the owner's own design (source: the Cipher_Lacuna_Brand_Pack folder beside this project). The files here are unchanged copies; don't redraw them.

| File | From the brand pack | Used for |
| --- | --- | --- |
| `logo.svg` | `logo.svg` | Header mark before the wordmark (34 px tall, 30 px on phones). Same file on light and dark themes. The file has 10 units of empty space on each side of its 64-unit square, so `style.css` pulls the image out by 10/64 of its size (`.brand-logo` margin) to line the visible cube up with the content edge; adjust that if the logo file changes. |
| `favicon.svg` | `favicon.svg` | Browser tab icon. |
| `icon-32.png` | `icon-32.png` | Tab icon for browsers without SVG favicon support; listed before the SVG in the page head, so browsers that support SVG keep using `favicon.svg`. |
| `apple-touch-icon.png` | `icon-180.png` | iPhone / iPad home-screen icon (`<link rel="apple-touch-icon">`). Its background is transparent; iOS shows transparent pixels as black. |
| `icon-512.png` | `icon-512.png` | Large icon, published with the site for reuse. |
| `og.png` | generated | Share preview (Open Graph / X card), 1200 x 630: the logo, "Cipher Lacuna" and both taglines on the light background. Regenerate with `python scripts/make_og.py` (needs Playwright) when the logo or the taglines change. |
| `app-qr.svg`, `app-qr.png` | generated | QR code for `https://cipherlacuna.ae/apk`, the app share page (the SVG is embedded in that page; the 1024 px PNG is for printing or sending). Regenerate with `python scripts/make_app_share.py` (needs Playwright). |
| `app-og.png` | generated | 1200 x 630 link preview of the app share page (WhatsApp, X, Telegram): logo, "Android app" in both languages and the QR code. Same script. |
| `app-card.png` | generated | 1080 x 1350 picture to post in a chat or a status: logo, what the app has, the QR code and the link. Same script. |

How the build uses them (`python scripts/build.py`):

- `logo.svg` and `favicon.svg` are tidied (the build removes `<script>`, `<foreignObject>`, event-handler attributes, links and references outside the file) and embedded in the page as images (`data:image/svg+xml`), never as inline markup. An SVG shown as an image cannot run scripts or load anything from the network, so a file that slips past the tidy-up still can't do harm. Consequences: the logo can't pick up the page's colours (no `currentColor` theming), and the file must be well-formed SVG/XML; the build adds the `xmlns` declaration if it is missing. Keep the files self-contained (shapes, gradients and embedded data only; no external fonts or images).
- Every `*.png` in this folder is copied to `dist/brand/` (and to `brand/` beside the `--standalone` copy), because the home-screen icon and the share preview are fetched by URL.
- The Open Graph and X tags in `web/template.html` point to the live site, `https://cipherlacuna.ae/`, with `og:image` at `brand/og.png`. Change them there if the site moves.

Without `favicon.svg` the site falls back to a neutral gradient square; without `logo.svg` the header shows the wordmark alone.
