# Product
<!-- impeccable:product-schema 1 -->

## Scope
Kinect Hoard is a menu of working Kinect modes and reusable reference implementations,
not a scanner-only landing page. Camera, body/avatar/Blender, scanner, face,
audio/voice, gestures/games, geometry, recording/replay, bridges and diagnostics
must all remain visible, with executable operations and shared MCP tools. Luis asked for
a scanner with real-time growing textured mesh, movable camera and fixed camera
modes. Current priority is One fixed on a tripod, with a person turning naturally.
He rejected earlier voxelated, split, artifact-filled busts; quality is not accepted.

## Platform
web

The Hoard Hub launches the loopback web interface. Native WinForms studio and live
scanner remain available. A native x64 process owns camera and Fusion; Python
publishes the same operations through stdio MCP and the common HTTP agent contract.

## Users and work
Luis operates camera preview, starts, pauses and finishes scans, inspects the
colored surface and exports OBJ/MTL/PNG. Faustus and other agents use the same
capabilities. Opening the interface, catalogue or MCP must not start a camera.
The top-level catalogue covers all 26 documented capabilities. A logo identifies
the Hoard in its header and Hub entry. No placeholder modes or hidden native menu
items substitute for a discoverable, executable workflow.

## Visual direction
An ordinary Hoard in the existing family: shared HoardLink charcoal theme, serif
wordmark, sans controls, restrained mint accent from Kinect's native studio,
common official Faustus icon and relay, no slogans. Operate mode. Preserve all
existing studio features. The web dashboard is the primary Hub entry.

## Truth and constraints
Both camera previews and a stationary 360 chair export have been physically
tested. Natural person rotation remains experimental and has known tracking
failures. No nonrigid posture correction or semantic object segmentation.
Do not present successful file export as proof of commercial scanner quality.
No driver changes, no autostart, no local text model, no push.
