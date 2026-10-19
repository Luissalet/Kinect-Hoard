---
name: Kinect Hoard
description: Shared Hoard family design for the local Kinect scanner web interface.
colors:
  primary: "#7adac4"
  primary-hover: "#a0e6d6"
  primary-ink: "#14201e"
  deep: "#171919"
  sunken: "#121414"
  surface: "#1e2121"
  elevated: "#282b2c"
  hover: "#303334"
  border: "#3a3d3e"
  border-hover: "#5e6364"
  text: "#e1eaec"
  text-muted: "#b4bcbe"
  text-dim: "#9ba4a6"
typography:
  body:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "16px"
    lineHeight: 1.45
  label:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "13px"
rounded:
  control: "6px"
  viewport: "8px"
spacing:
  compact: "8px"
  control-gap: "12px"
  view-gap: "20px"
  desktop-inset: "28px"
  mobile-inset: "16px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  viewport:
    backgroundColor: "{colors.sunken}"
    rounded: "{rounded.viewport}"
---

# Design System: Kinect Hoard

## Overview

**Creative North Star: "The Hoard Family Workbench"**

This web surface extends the existing Hoard family: charcoal working surfaces,
a mint Kinect accent, serif identity and readable sans controls. It gives camera
and reconstruction imagery most of the available space. The native Windows studio
remains a separate, preserved interface, opened explicitly from the web header.

The source of truth is `ui/scanner.html` plus the shared HoardLink
`hoard_link/ui/hoard-theme.css`, served by `hoard_server.py`. This document records
that web implementation; it does not prescribe a native studio redesign.

**Key Characteristics:**
- Shared family identity with a restrained Kinect accent.
- Flat working surfaces and clear control states.
- Large camera and colored-surface views.

## Colors

### Primary

Mint identifies the wordmark, primary scan action, current state, links and keyboard
focus. The brighter primary variant marks enabled primary-button hover; dark ink
keeps its text readable.

### Neutral

Deep charcoal forms the page, the surface tone forms the header, and sunken charcoal
holds camera imagery. Elevated and hover tones distinguish controls. Light text,
muted labels and dim helper text form the reading hierarchy; borders mark groups
and viewport edges.

**The Family Palette Rule.** Consume the shared Hoard theme and keep the Kinect
mint override local to this app. Preserve the official Faustus launcher's own mark
and color instead of recoloring it as a scanner control.

## Typography

The wordmark uses the shared serif stack (`Cinzel`, `Iowan Old Style`, Charter,
Georgia, `Liberation Serif`, `Noto Serif`, `Times New Roman`, serif), at 23px and
weight 600. The shared CSS names these fonts; this surface does not download font
assets. The reviewed browser rendered an installed serif fallback.

The page title is sans (26px, weight 600); view titles are sans (16px, weight 600).
Body and controls follow the body token. Labels use the label token; navigation,
help and metrics use 14px. Metrics use tabular numerals.

**The Identity and Work Rule.** Reserve the serif treatment for identity; keep task
titles, instructions and controls in the shared sans stack.

## Layout

The header groups identity, Hoard Hub, API, MCP tools and the explicit native-studio
action. The web working area is centered with a maximum width of 1800px. Settings,
scan actions, views and status appear in that order.

Above 800px the page uses the viewport height and allocates remaining height to two
views, with camera-to-reconstruction columns of 1:1.55 and the view-gap token.
Desktop horizontal insets follow the desktop-inset token. At 800px and below the
header stacks, controls wrap and both views form one column with a 4:3 aspect ratio;
mobile horizontal insets follow the mobile-inset token. The page then scrolls.

## Elevation & Depth

The scanner work area uses tonal separation and thin borders, without card shadows.
The common Faustus launcher retains the shared integration's styling. Do not infer
a new shadow system from that independently provided control.

## Shapes

Controls have modest rounded corners from the control token; image viewports use
the viewport token and clip their contents. One-pixel borders structure settings,
status, controls and image boundaries. Imagery is contained without cropping.

## Components

**Buttons and selects.** Controls share a minimum height of 42px and padding of
9px 13px. The mint scan button is the primary action; ordinary actions use elevated
charcoal. Enabled hover changes surface and border. Disabled controls use opacity
0.46. Keyboard focus is a 2px mint outline offset by 3px. Selects have visible
labels and expand within wrapping mobile settings.

**Image viewports.** Camera and colored surface each have a title, contextual hint
and centered empty state. Camera selection uses a crosshair; reconstruction orbit
uses a grab cursor and pointer capture. Empty-state copy refers to the selected
sensor generically. The selection hint distinguishes One person masking from the
click-to-select path for other configurations.

**Status and help.** A bordered status row combines a mint state name, a plain
description and subdued numeric metrics. Errors appear as text alerts. A compact
disclosure exposes experimental tracking guidance. Finished exports appear as
download links without implying that mesh quality has been accepted.

**Family integration.** HoardLink installs the official Faustus launcher and relay;
the scanner supplies current view context. Retain the common icon-only launcher
with accessible name `Faustus`. Opening the page or inspecting MCP tools does not
connect a camera.

## Do's and Don'ts

- **Do** extend the shared Hoard family theme and preserve the native studio entry.
- **Do** keep control labels accurate for the selected sensor and subject.
- **Do** expose camera state, disabled actions and experimental tracking limits.
- **Don't** add slogans or substitute a new visual identity for the family theme.
- **Don't** present export completion or UI review as acceptance of scan quality.

The final visual review disposition was **ship**, with the two contextual-label
fixes resolved. Reviewed evidence: `.impeccable/review/selection-360.png` and
`.impeccable/review/mobile.png`; current source governs copy where an earlier
capture differs. Physical scan quality remains outside that visual verdict.
