# Product
<!-- impeccable:product-schema 1 -->

## Scope
Kinect Hoard is the local Windows Kinect studio and 3D scanner. Luis asked for
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
