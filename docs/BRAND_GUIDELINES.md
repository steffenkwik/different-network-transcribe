# Different Network Transcribe — UI Brand System

**Updated:** 2026-07-16
**Scope:** Windows desktop application.

## Intent

The interface is calm, technical, and distinctly Different Network: DN black
surfaces keep attention on the work, official orange identifies the next safe
action, and chilli red-orange communicates a controlled warning or irreversible
action. Information remains readable first, branded second.

## Official assets

`app/ui/brand.py` renders the official Different Network Academy wolf mark from
`assets/brand/dn-favicon.svg`. The installer, desktop shortcut, and app window
use the paired `assets/brand/dn-favicon.ico`. The mark is used unchanged at
32–44 px on a plain dark surface; do not stretch, rotate, shadow, or recolour it.

## Tokens

| Token | Hex | Role |
|---|---|---|
| Canvas | `#060606` | Dominant DN black page background |
| Sidebar | `#0E0E0E` | Navigation surface |
| Surface | `#141414` | Cards and dialogs |
| Raised surface | `#1C1C1C` | Controls and elevated panels |
| Border | `#303030` | Dividers and outlines |
| Primary orange | `#FF4D00` | One primary action per page and focus |
| Chilli red-orange | `#FF2D1A` | Safe stop and controlled attention |
| Danger | `#FF4D4D` | Explicit destructive action |
| Primary text | `#F5F5F5` | Headings and body text |
| Muted text | `#9A9A9A` | Supporting explanations |

Functional states always have an explicit text label; colour is never the only
signal. Keyboard focus is a visible 2 px DN-orange outline. Delete uses a
distinct red treatment plus a confirmation dialog.

## Typography and interaction

- **Archivo** is the UI/body family, **JetBrains Mono** is for compact labels
  and metadata, and **Chakra Petch SemiBold** is for buttons—matching Different
  Network Academy. The OFL font files and their full licenses ship with the app.
- The layout uses a 4/8 px rhythm, 27 px page titles, 18 px section titles, and
  14 px body copy.
- Each main page has one DN-orange primary action. Buttons are at least 40 px
  high and expose hover, pressed, disabled, and focus states.
- Before a worker starts, a modal requires a locally installed model and a
  deliberate file selection. The default safe batch is at most 20 files.
- **Semua Transkrip** supports multi-row selection with Ctrl/Shift. Clearing a
  selected history removes derived transcript data only; source audio, source
  folders, fingerprints, and chat metadata remain untouched.

## Research inputs

- [W3C WCAG 2.2 contrast minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum)
- [W3C WCAG focus appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance)
- [Qt Style Sheet Syntax](https://doc.qt.io/qt-6/stylesheet-syntax.html)
