# Brand slot

The site shows the text wordmark **Cipher AI Knowledge** in the header. The logo is being designed by the owner; nothing here is a logo.

To add it, drop these files into this folder and rebuild (`python scripts/build.py`):

| File | Used for | Guidance |
| --- | --- | --- |
| `logo.svg` | Shown in the header as an image, before the wordmark (about 30 px tall) | Square mark, `viewBox` around `0 0 64 64`. Must read on both light and dark backgrounds (the header follows the site theme) and stay legible at 16 px. No text needed, the wordmark sits next to it. |
| `favicon.svg` | Browser tab icon | Square, `viewBox` around `0 0 32 32` or `0 0 64 64`, simple enough for 16 px. |

Without `favicon.svg` the site uses a neutral placeholder: a rounded square in the brand gradient (#42208d, #753aca, #d52f89) with no letter or symbol. Without `logo.svg` the header shows the wordmark alone.

The build tidies both files (it removes `<script>`, `<foreignObject>`, event-handler attributes, links and references outside the file) and then embeds each one as an image (`data:image/svg+xml`), never as inline markup. An SVG shown as an image cannot run scripts or load anything from the network, so a file that slips past the tidy-up still can't do harm. Two consequences: the logo can't pick up the page's colours (no `currentColor` theming), and the file must be well-formed SVG/XML as design tools export it; the build adds the `xmlns` declaration if it is missing. Keep the files self-contained: shapes, gradients and embedded data only, no external fonts or images (convert text to outlines). The `viewBox` sets the proportions.
