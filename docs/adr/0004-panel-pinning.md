# ADR 0004: Pinning the panel with a KWin rule

- **Status:** Accepted
- **Date:** 2026-10-25
- **Context task:** 1.4 (issue #40); builds on ADR 0003

## Context

Wayland windows can't place themselves, so Recon pins its panel to the right edge with a KDE window rule, opt-in. Three questions came up while building it:

1. A KWin rule that *forces* position and size also stops the user dragging the window wider, which clashes with task 1.3's "user-resizable, width remembered".
2. When should Recon ask?
3. How tall should the panel be?

## Findings on Tyler's desktop

- A rule matching the app ID and the title "Recon Panel" exactly, with the position forced, put the panel at x=860, 420 px wide. The fallback KWin script put it at x=900, 380 px wide. Both were checked through KWin itself.
- On Wayland, `QScreen.availableGeometry()` is the whole screen (1280×720) whatever the taskbar does, so Qt can't say how tall the panel should be.
- KWin's work area (`clientArea(MaximizeArea)`) is also the full 720 px here. Tyler's Plasma taskbar is floating and auto-hides (`panelVisibility=1`), so it reserves no space.
- Unpinning wrote `count=0` where Tyler's file had no `count` key. It's now deleted when no rules remain, and `kwinrulesrc` matched the backup byte for byte after unpinning.

## Decision

1. **Pinned means fixed** (Tyler's choice). The rule forces the position, and forces the width by setting the minimum and maximum width equal. Dragging does nothing; the width changes from Settings' panel-width control (task 1.14), and Recon rewrites the rule 500 ms after a change. With pinning off, the panel drags freely and remembers its width (task 1.3).
2. **Height from vertical maximise, not a number.** The rule forces `maximizevert`, so KWin fills exactly the work area: the full screen with an auto-hiding taskbar, or the space above it with an always-visible one. The fallback script asks KWin for the same area.
3. **Ask once, at first launch, over Home** (Tyler's choice), before any room starts: "Pin the Recon panel to the right edge of your screen while you work?", with **Pin the panel** (the primary button) and **Not now**. "Not now" and Escape both turn pinning off. The setting is `kwin_pinning` (`ask`, `on` or `off`) in `settings.toml`.
4. **Fallback:** if writing the rule or reloading KWin fails, a KWin script (`$XDG_DATA_HOME/recon/kwin-panel.js`, 0600) pins the panel for the session. It's reloaded at each launch while pinning is on. If both fail, a calm toast says so, and the panel opens as a normal window.
5. **Clean removal:** unpinning deletes every key in Recon's `recon-panel` group (including the older rule shape's keys), removes it from `General/rules` and `General/Order`, drops `count` when no rules are left, reloads KWin, and unloads and deletes the script. Other groups are never touched.
6. **Off the UI thread:** the KDE commands run on Qt's thread pool, and the result comes back as a signal.

## Consequences

- Settings (task 1.14) needs the pinning on/off switch (`Pinning.unpin()` and `Pinning.pin()`) and the panel-width control, which re-pins.
- The rule's x position comes from the screen's geometry, so a taskbar on the *right* edge would overlap the panel. That's not Tyler's layout. If it ever becomes one, the rule can switch to the work area that KWin reports.
