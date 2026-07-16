# Different Network Transcribe — UI Brand System

**Updated:** 2026-07-16
**Scope:** the Windows desktop application. This is a product-interface visual system, not a substitute for an approved corporate logo package.

## Intent

The application is a private, long-running productivity tool. Its interface must feel calm and technical rather than flashy: the dark canvas keeps attention on the work; warm yellow identifies the next safe action; orange signals attention or a controlled stop. Information remains readable first, branded second.

## Product mark

`app/ui/brand.py` draws a compact **DN** mark using two linked paths:

- Yellow path: the `D` side, meaning the user-controlled starting point.
- Orange path: the `N` side, meaning the connected processing path.
- The mark is a provisional in-app visual mark. It is intentionally isolated in one widget so an approved Different Network SVG can replace it without changing application flows.

Use the mark at 32–44 px, on a plain dark surface, with one mark-height of clear space. Do not stretch, rotate, add shadows, or use a gradient on it.

## Color tokens

The tokens are implemented once in `app/ui/theme.py`; page code must use object names and the shared stylesheet rather than introducing ad-hoc colours.

| Token | Hex | Role |
|---|---|---|
| Canvas | `#0D0F12` | Dominant black page background |
| Sidebar | `#111419` | Navigation surface |
| Surface | `#171B20` | Cards and dialogs |
| Raised surface | `#20262D` | Controls and elevated panels |
| Border | `#37414C` | Dividers and component outline |
| Primary yellow | `#F8C63D` | One primary action per page, focus and brand emphasis |
| Accent orange | `#F28C28` | Safe-stop and controlled attention states |
| Primary text | `#F7F8FA` | Headings and body text |
| Muted text | `#B8C0CA` | Supporting explanations |
| Success | `#53C78A` | Positive state with an accompanying label |
| Danger | `#F27272` | Failure state with an accompanying label |

Measured contrast against the canvas: primary text **18.06:1**, muted text **10.45:1**, and yellow **12.01:1**. Black text on the yellow CTA is **11.55:1**; dark text on orange is **7.68:1**. These pairs exceed WCAG AA normal-text contrast. Functional states always retain an explicit text label; colour is never the only signal.

## Typography and spacing

- Use the Windows-native `Segoe UI` family so the installer does not need to bundle a remote font.
- Sizes: 27 px page title, 18 px section title, 14 px base text, 12 px only for metadata/supporting copy.
- Weights: 700 for page hierarchy, 600 for actions and navigation, 400 for body copy.
- Use the 4/8 px rhythm: components use 8/12/16 px internal spacing; page sections use 14–28 px separation.
- Do not use emoji as structural icons. The custom mark is painted as vectors by Qt.

## Interaction rules

1. Each main page has a single yellow primary action. On Beranda it is **Siapkan & Mulai Transkripsi**.
2. Before any worker starts, a modal requires a model choice and shows selectable files. The default mode is a safe batch of no more than 20 files.
3. A user can opt into all incomplete files only through a separate checkbox and a written acknowledgement. This keeps large archives from being started accidentally.
4. Pausing, safe stopping, retrying, exporting, source selection, backup, and detail editing remain available; branding must never hide product functions.
5. Buttons are at least 40 px high and show hover, pressed, disabled, and a high-contrast keyboard focus state.
6. Large lists remain paged; the setup dialog caps its preview at 250 rows and does not load transcript bodies.

## Accessibility verification

- The focus outline is a 2 px yellow border. It contrasts with both dark components and their surrounding surface.
- Keyboard tab order follows the visual order: sidebar, page actions, filters/tables, dialogs.
- Model installation status is communicated by text, not only disabled colour.
- Preflight errors explain how to recover: install a model, scan files, select 1–20 files, or expressly confirm the bulk run.
- No decorative animation is needed for a long-running desktop task; progress is represented by text plus a bar.

## Research inputs

- [W3C WCAG 2.2 contrast minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum) informed the 4.5:1 text threshold.
- [W3C WCAG focus appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance) informed the visible 2 px focus treatment.
- [Qt Style Sheet Syntax](https://doc.qt.io/qt-6/stylesheet-syntax.html) supports the object-name and dynamic-property styling model used by the PySide6 interface.
