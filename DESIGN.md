---
name: Kinect Hoard
description: Shared Hoard family design for the Kinect modes workspace and live scanner.
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
  error: "#efa399"
typography:
  identity:
    fontFamily: "'Cinzel', 'Iowan Old Style', Charter, Georgia, 'Liberation Serif', 'Noto Serif', 'Times New Roman', serif"
    fontSize: "23px"
    fontWeight: 600
  headline:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.2
  title:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 600
  body:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "16px"
    lineHeight: 1.45
  label:
    fontFamily: "'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans', 'Liberation Sans', Arial, sans-serif"
    fontSize: "13px"
  code:
    fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
    fontSize: "13px"
rounded:
  control: "6px"
  viewport: "8px"
spacing:
  field-gap: "6px"
  compact: "8px"
  control-gap: "12px"
  mobile-inset: "16px"
  view-gap: "20px"
  group-gap: "24px"
  section-gap: "28px"
  desktop-inset: "36px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  field:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  navigation-active:
    backgroundColor: "{colors.elevated}"
    textColor: "{colors.primary}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
  viewport:
    backgroundColor: "{colors.sunken}"
    rounded: "{rounded.viewport}"
---

# Design System: Kinect Hoard

## Overview

**Creative North Star: "The Hoard Family Workbench"**

Kinect Hoard extends the pinned Hoard family world: charcoal working surfaces,
mint Kinect accents, serif identity and readable sans controls. It is an Operate
surface with a permanent mode menu, practical controls and implementation
references. The sensor-shaped `app-icon.svg` identifies the workspace and scanner.

The web system is recorded from `ui/workspace.html`, `ui/workspace.css`,
`ui/workspace.js`, the preserved `ui/scanner.html` and the shared HoardLink theme.
The desktop studio remains available explicitly; its native design is outside
this document's scope. The implementation extends the existing world without
introducing a new visual direction.

**Key Characteristics:**
- Shared family identity with a restrained Kinect accent.
- Flat, divided work areas with persistent mode navigation.
- Actual camera and avatar views with explicit reader and empty states.
- Executable mode actions, local source references and retained operation results.

### Documentation change log

2026-10-19, workspace/task 944: replaced the obsolete scanner-only description with
the ten-mode menu and shared work controls. Recorded the current selected-versus-
active reader state, zero-body avatar state and queued job history. Removed the
previous scanner-only ship verdict. First-round captures in
`.impeccable/review944/` document desktop, mobile, the 1890px view and camera;
source governs subsequent state fixes. Final reviewer944 disposition is **ship**
for this bounded web workspace: operation history, explicit active/pending stream
and zero-body avatar states, and design-document truth are resolved. This visual
verdict does not approve scan quality. Natural human rotation scan quality remains
experimental and unaccepted.

## Colors

The shared charcoal palette separates work areas through tone; Kinect Mint marks
identity, selection and actionable emphasis.

### Primary

- **Kinect Mint** (`primary`): wordmark, primary actions, links, active navigation,
  keyboard focus and scanner state.
- **Bright Mint** (`primary-hover`): enabled primary-action hover.
- **Deep Mint Ink** (`primary-ink`): readable text on mint buttons and selection.

### Secondary

- **Soft Coral Error** (`error`): textual operation and connection failures. Error
  messages remain readable text rather than relying on color alone.

### Neutral

- **Deep Charcoal** (`deep`): page background.
- **Sunken Charcoal** (`sunken`): image wells, source excerpts and result data.
- **Surface Charcoal** (`surface`): header, sidebar and hovered mode rows.
- **Elevated Charcoal** (`elevated`): controls and active navigation.
- **Hover Charcoal** (`hover`): enabled ordinary-control and navigation hover.
- **Graphite Line** (`border`): work-area dividers, fields and viewport boundaries.
- **Light Graphite Line** (`border-hover`): enabled control hover boundary.
- **Cool Light Text** (`text`): headings, control text and mode names.
- **Muted Cool Text** (`text-muted`): descriptions, labels and ordinary navigation.
- **Dim Cool Text** (`text-dim`): captions, file metadata and technical identifiers.

**The Family Palette Rule.** Consume the shared Hoard theme and keep the Kinect
mint override local to this app. Preserve the official Faustus launcher's own mark
and color instead of recoloring it as a Kinect control.

## Typography

**Display Font:** the shared serif stack, reserved for the identity wordmark.
**Body Font:** the shared sans stack for work and navigation.
**Label/Mono Font:** the label and code stacks in the frontmatter.

The application names font stacks without downloading fonts. Installed fallbacks
therefore determine the rendered face. Serif identity and compact sans working
text keep the family resemblance while allowing dense controls and references.

### Hierarchy

- **Identity:** frontmatter identity token; mobile workspace wordmark reduces to
  21px at 700px. The sensor icon is 40px, reducing to 34px on mobile.
- **Headline:** frontmatter headline token; mobile and scanner titles use 26px.
- **Title:** frontmatter title token for workspace section headings; action titles
  and mode names use 17px. Scanner view titles use 16px, weight 600.
- **Body:** frontmatter body token; paragraphs generally stop at 75ch, with the
  workspace introduction allowing 85ch.
- **Navigation and support:** 14px mode descriptions, navigation and reader state.
- **Labels and captions:** frontmatter label token; source excerpts and structured
  data use compact 13px text. Frame and scanner metrics use tabular numerals.

**The Identity and Work Rule.** Reserve the serif treatment for identity; keep task
titles, instructions and controls in the shared sans stack.

## Layout

The workspace header is 76px high on desktop and groups the sensor logo, identity,
Hoard Hub/API/MCP links and actual device status. A two-column shell places the
238px sidebar beside a main area capped at 1700px. Main insets are 30px vertically
and the desktop-inset token horizontally, with 88px bottom space. At 1100px and
above the sidebar sticks within the viewport and scrolls independently.

The home index has ten divided rows: Cámara; Cuerpo, esqueleto y avatar; Escáner
3D; Rostro; Audio y voz; Gestos e interacción; Geometría y coordenadas; Grabación y
reproducción; Integraciones y referencias; Sensores y diagnóstico. Each row has a
name, description and opening cue. Sidebar navigation also retains files, all
references, sensor detection and the explicit desktop-studio action.

Each mode groups its heading, stream toolbar where applicable, reader state,
live views, actions, guide and expandable references. Actions use a tool selector
beside a form, with two field columns. Body and interaction can show camera and
avatar side by side. References use divided text sections rather than a card grid.
Activity follows the current route's content and preserves separate job entries.

At 1000px and below the sidebar narrows to 200px, row contents stack, tools wrap
above their forms and camera/avatar become one column. At 700px and below the
header wraps, the shell becomes a vertical flow, the sidebar becomes a horizontally
scrolling navigation strip, fields become one column and main uses mobile insets.
The document scrolls vertically; long source text and filenames wrap or scroll
inside their own regions. Live wells are 280px high on mobile; desktop wells use
`min(42vh, 400px)` with a 230px minimum.

The separate `/scanner` route retains its two-view workspace and a return link to
all modes. Its maximum width is 1800px, with camera-to-surface columns of 1:1.55.
Above 800px it fills the viewport and gives remaining height to imagery; at 800px
and below the header and 4:3 views stack. Scanner settings and actions wrap.

## Elevation & Depth

The workspace and scanner use tonal separation and one-pixel boundaries without
card shadows. No new shadow or animation vocabulary is implemented. The common
Faustus launcher retains its independently provided styling; it does not define
a new workspace elevation system. Hover and focus changes are immediate.

## Shapes

Controls and active navigation use the modest control radius; live image wells
use the viewport radius and clip contained imagery without cropping. Index rows,
reference sections, tool areas, files and Activity rely on horizontal dividers.
The sensor asset has its own rounded square silhouette; retain that asset rather
than treating its geometry as the shape of every work container.

## Components

### Buttons

Practical, compact actions with a minimum height of 42px. Workspace controls use
the frontmatter padding; scanner controls use 9px 13px. Primary controls use mint
with dark ink and weight 600; ordinary controls use elevated charcoal. Enabled
hover changes the surface and boundary. Workspace disabled opacity is 0.5;
scanner disabled opacity is 0.46. Keyboard focus is a 2px mint outline offset by
3px. Sidebar utility buttons become 36px high on mobile; file actions use 34px.

### Inputs / Fields

Visible labels sit above elevated charcoal controls with a 6px gap. Stream and
sensor selects accompany an explicit Connect action. Schema-derived operation
forms provide selects, text/number inputs and JSON textareas. Textareas use the
code stack, resize vertically and span both desktop columns. Invalid JSON appears
as a text alert. Search filters references by title and Toolkit sample names.

### Navigation

The persistent mode navigation uses muted text at rest, hover charcoal on hover,
and mint text over elevated charcoal for `aria-current="page"`. The active tool
uses `aria-pressed` with the same tonal emphasis. The home index exposes all ten
modes as full linked rows; the mobile strip scrolls independently while the full
index keeps every mode available in the document. Route changes return the page to
the top and focus the main work area without an additional scroll.

### Live image containers

Sunken wells contain actual frame imagery, a textual empty state and subdued
captions. The header states the active sensor and stream. The work area separately
states the selected sensor/stream; a mismatch is called a pending selection and
the previous preview is hidden until Connect applies it. Changing a selector does
not itself open or switch the reader.

Body mode defaults to Color registered with depth (`ColorDepth`), supplying RGBD
and joint data; Esqueleto remains available. The avatar appears only when the
matching active reader supplies body tracking and a positive body count. Zero
bodies explicitly asks the user to stand in front of One; unsupported readers
explain which One streams provide the avatar. No decorative avatar substitutes
for missing tracking.

### Guides and source references

Every mode has a recipe, executable actions and expandable references. Reference
sections expose output descriptions, Toolkit sample names, exact local source
links and a lazily loaded contract excerpt. All references are also searchable
from a dedicated route. Source text uses a scrollable sunken preformatted region.

### Activity and saved files

Submitted operations show an in-progress status and then separate expandable
Activity entries, retaining each returned job ID in the entry data. Queued,
running, finished, partial and error outcomes remain distinct. Newer jobs appear
first; open entries are retained and the newly submitted job opens automatically.
Structured results and saved artifact links remain attached to their own job.
Partial output explicitly says the capture is incomplete. Files have download
links, size/date metadata and KHR replay/inspection actions where supported.

### Live scanner

Settings identify movement, sensor and subject before connection; state determines
enabled scan, pause, finish and camera-follow actions. Camera selection uses a
crosshair; the accumulated colored surface uses a grab cursor and pointer capture
for orbit. Status combines a mint state, explanation and tabular metrics. A help
disclosure explains tracking recovery and experimental limits; finished scans
expose OBJ, MTL, PNG and PLY downloads.

### Family integration

The sensor icon and wordmark link home. Matching PNG and ICO exports of the
authored SVG supply the Hub and native icon. HoardLink supplies the official icon-only
Faustus launcher with accessible name `Faustus`, relay and current-view context.
Opening the web interface, catalogue or MCP does not connect a sensor.

## Do's and Don'ts

### Do:

- **Do** extend the shared Hoard family theme and preserve the native studio entry.
- **Do** keep all ten modes discoverable with their actions, guides and source references.
- **Do** distinguish selected controls from the actual reader and hide mismatched previews.
- **Do** state zero-body, queued, partial and error outcomes in readable text.
- **Do** retain separate operation results and their saved artifact links in Activity.
- **Do** keep keyboard focus visible and mobile overflow inside the relevant region.

### Don't:

- **Don't** add slogans or substitute a new visual identity for the family theme.
- **Don't** present export completion or UI review as acceptance of scan quality.
- **Don't** display a placeholder avatar as detected motion or start a sensor on page load.
