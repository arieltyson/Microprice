# Accessibility

The Microprice dashboard targets WCAG 2.2 Level AA.

## Supported Environments

- Current Chrome, Firefox and Safari on desktop, at widths from 320 CSS pixels upward
- VoiceOver with Safari on macOS and NVDA with Firefox on Windows
- Keyboard-only navigation and browser zoom up to 400%

## What the Dashboard Does

- Every chart is paired with a text summary and a data table that holds the same values.
- The order book ladder is a semantic table with row and column headers.
- Colour never carries meaning alone: bids sit on the left, asks on the right, P&L carries a sign and a zero line, and feed gaps are labelled.
- All colour pairs are checked against WCAG contrast ratios by automated tests, including the high-contrast themes.
- Nothing flashes, and transitions are disabled when the operating system requests reduced motion.
- Type is set in rem units, so browser font settings and zoom apply everywhere.

## Known Limitations

- Canvas charts are hidden from assistive technology; their data tables are the accessible alternative.
- The dashboard has no audio or video content, so captions and audio descriptions do not apply.

## Reporting a Barrier

Open an issue describing the barrier, the view, your browser and the assistive technology you use. Accessibility fixes take priority over new dashboard features.
