# ADR 0003: Desktop integration (global shortcut portal, KWin rule, display scale)

- **Status:** Accepted
- **Date:** 2026-10-24
- **Context task:** 0.7c (issue #6)

## Context

Recon needs hold-to-talk on F9 while the browser has focus, and a side panel pinned to the right edge on Wayland. CLAUDE.md planned to call the XDG GlobalShortcuts portal directly through QtDBus, and to pin the panel with a KWin rule matched on the app ID and the window title. Phase 0 tested both on the user's machine (Plasma 6.8.1, xdg-desktop-portal 1.22.1, GlobalShortcuts portal version 2).

## Findings

**Portal over QtDBus doesn't work from Python.** `BindShortcuts` takes `a(sa{sv})`. QtDBus can only marshal an array of structs whose element type is registered with `qDBusRegisterMetaType`, which PySide6 doesn't expose. The marshaller refuses ("type 'QDBusArgument' is not registered with D-Bus"). Separately, `QDBusArgument << str` marshals as `as`, not `s`, and `<< int` as `q`; only `appendVariant` writes a plain string.

**jeepney works.** It takes the D-Bus signature explicitly (`oa(sa{sv})sa{sv}`), and KDE's portal backend logged the call exactly as intended. The whole sequence runs on one connection: `Registry.Register` → `CreateSession` → `BindShortcuts` → `Activated`/`Deactivated`. It passed from a terminal and from a `.desktop` launch, with true press and release events (holds of 667–1036 ms).

**Registration needs an installed `.desktop` file.** `Registry.Register` fails with "App info not found" unless `~/.local/share/applications/<app-id>.desktop` exists. Qt 6.11 also calls `Register` by itself on its own D-Bus connection when `setDesktopFileName` is set; that's harmless, but Recon must still register on the connection it uses for the portal.

**A missed dialog leaves a dead binding.** If KDE's permission dialog isn't answered before the portal session closes, KDE stores the shortcut with no key (`voice=none,F9,…`). Later `BindShortcuts` calls are then "accepted" with an empty `trigger_description` and show no dialog, so F9 never fires. Clearing the entry (kglobalaccel `unregister`) brings the dialog back.

**The KWin rule works as designed.** With `wmclass` (exact) = the app ID and `title` (exact) = the panel title, only the panel was forced to the right edge at full height; a second window with the same app ID stayed free. KWin appends applied rules to `General/Order` by itself, so removing a rule must clean `Order` as well as `rules` and `count`.

**Display scale.** The screen is 2560×1440 at 200% scale, so the logical desktop is 1280×720. A 420 px panel is 840 physical px, a third of the width; the spec's "about 2,100 px left for the room" assumed 100% scale. After trying the 420 px test panel, 420 px was kept.

## Decision

1. **jeepney for the GlobalShortcuts portal** (MIT, pure Python, no dependencies). It replaces QtDBus for this use. `services/portal.py` will own one blocking jeepney connection on a worker thread and post events to Qt with queued signals, so asyncio never meets Qt's event loop. This is the rationale CLAUDE.md gave for avoiding `global-shortcut-portal`.
2. **Register first, on the portal connection,** after making sure the `.desktop` file is installed (task 1.15 installs it; Phase 5 checks it).
3. **Detect an unbound shortcut.** When `BindShortcuts` returns an empty trigger, Recon says so plainly and offers to fix it: the portal's `ConfigureShortcuts` (version 2) opens KDE's shortcut settings. The panel's mic button keeps voice usable meanwhile.
4. **KWin rule as tested,** with `Order` cleanup on removal (task 1.4).
5. **Panel width stays 420 px** (decided 2026-10-24, after trying it), resizable from 360 to 520 as the spec says.

## Consequences

- CLAUDE.md's stack row for the global hotkey now names jeepney. Notifications stay on QtDBus for now (`Notify` is `susssasa{sv}i`, which needs no struct arrays); task 2.5 confirms.
- jeepney talks to the session bus over a local Unix socket. The network-import test only bans network modules, and jeepney is confined to `services/`, which the threat model's D-Bus entry point (E7) covers.
- Smoke tests: `scripts/smoke/shortcut.py` and `scripts/smoke/kwin_rule.py` (with `apply`, `windows`, `geometry` and `remove`).
