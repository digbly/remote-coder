# Mobile Interface Plan

Plan for a responsive, touch-friendly mobile interface for Remote Coder,
delivered as a responsive web app reusing the existing PWA setup.

Priority features on mobile: **AI chat (primary), Git/PR status, terminal, and
project/worktree management**.

## 1. Current state and mobile blockers

| Area | Current implementation | Mobile problem |
| --- | --- | --- |
| Shell | `IdeShell.tsx:225` — `flex h-screen w-screen`, fixed three-column layout | Overflows on narrow viewports |
| Sidebar | Fixed width via inline `style={{ width }}` (`Sidebar.tsx:460`); actions via right-click context menu (`Sidebar.tsx:392`) and `window.confirm` (`:418`) | No context menu on touch; small hit targets |
| RightPanel | Fixed width; explorer/git/check tabs (`RightPanel.tsx:54`) | Consumes space; needs a bottom sheet |
| ResizeHandle | Mouse drag (`IdeShell.tsx:244`) | Meaningless on touch |
| TopTabs | Fixed `w-[180px]` tabs with overflow-x (`TopTabs.tsx:28`) | Usable but cramped; small close button |
| ChatPanel | Wrapping toolbar with four `<select>` controls plus composer (`ChatPanel.tsx:503,707`) | Best-suited feature; needs sticky composer and >=16px inputs |
| Terminal | xterm over WebSocket (`Terminal.tsx`) | Soft keyboard lacks Ctrl/Esc/Tab/Arrow keys |
| Settings | Fixed `w-48` sidebar (`SettingsPage.tsx:349`) | Needs to stack vertically |
| PWA | Manifest and icons already configured (`vite.config.ts:13`) | Missing `viewport-fit=cover` and safe-area handling |

### Cross-client state constraint (must decide)

`activeProjectId` is synced across all of a user's clients (`sync.ts:46`,
`workspaceStore.ts:38`), while `layout.*` and `activeId` are per-client
(`sync.ts:28-48`). Consequence: opening a project on the phone also switches the
project on the desktop. Mobile panel layout does not leak to desktop (good).

## 2. Strategy

**Hybrid approach.** Add a `useIsMobile()` hook (matchMedia) and render a
separate `MobileShell` below the `md` breakpoint (768px), keeping `IdeShell`
unchanged for desktop. Reuse child components (`ChatPanel`, `ProjectTerminal`,
`Sidebar`, panel tabs) and rebuild only the navigation frame. Rationale: avoid
cramming mobile logic into `IdeShell` (desktop regression risk), since layout is
driven by JS state rather than CSS alone.

## 3. Proposed mobile layout

```
+-----------------------------+
| menu  <project v>  cmd   ... |  Header: drawer | project picker | tab switcher | menu
+-----------------------------+
|                             |
|     Active tab content      |  Chat / Terminal / Editor / Diff / Git
|                             |
+-----------------------------+
| [Chat] [Terminal] [Git] [+] |  Bottom tab bar (horizontal scroll)
+-----------------------------+
```

- **Left drawer**: reuse `Sidebar` inside an overlay, closed by backdrop or Esc.
  Long-press triggers the existing context menu.
- **RightPanel** becomes a **bottom sheet** (explorer / source control / check).
- **Bottom tab bar** replaces `TopTabs` (pills, horizontal scroll, `+` opens
  `NewTabMenu`).
- Safe area: `env(safe-area-inset-*)` on header and bottom bar.

## 4. Feature detail

1. **AI chat (primary)** — `ChatPanel`: sticky bottom composer, 16px `textarea`,
   large Send/Stop buttons; move the provider/model/permission toolbar into a
   collapsible session-settings control; keep streaming, approval, and proposal
   logic unchanged.
2. **Git/PR** — reuse `SourceControlPanel`/`CheckPanel` in the bottom sheet;
   large buttons; use in-app confirmation for destructive actions instead of
   `window.confirm`.
3. **Terminal** — add a mobile keyboard toolbar (`Esc`, `Tab`, `Ctrl+Left/Right`,
   arrows, `PgUp/PgDn`, `Ctrl+C`) that calls `terminal.input()`; handle the soft
   keyboard occluding the viewport via `visualViewport`.
4. **Project/worktree** — manage from the drawer with explicit create/delete
   buttons instead of a context menu; render `NewProjectDialog` and
   `NewWorktreeDialog` as full-screen sheets.

## 5. Infrastructure changes

- `index.html:8`: add `viewport-fit=cover`; keep user zoom (accessibility).
- `index.css`: add `--safe-top`/`--safe-bottom` variables, `touch-action`, and
  a 44px minimum touch target.
- `vite.config.ts`: keep PWA; consider `display_override` and `orientation`.
- New `web/src/lib/useMediaQuery.ts` and `MobileShell.tsx`.
- i18n: every new string must be added to **both** `en.ts` and `vi.ts`.

## 6. Implementation phases

| Phase | Scope | Size |
| --- | --- | --- |
| 1 | Infrastructure: `useIsMobile`, viewport, safe area, `MobileShell` frame with tab bar and Sidebar drawer | S |
| 2 | Mobile chat (sticky composer, compact toolbar) | M |
| 3 | Git/Check bottom sheet and confirmation dialogs | M |
| 4 | Terminal keyboard toolbar and viewport fix | M |
| 5 | Full-screen project/worktree dialogs; stacked Settings | S |
| 6 | PWA polish (icons, splash, a11y, device testing) | S |

## 7. Risks and decisions to settle

- **Synced `activeProjectId`**: should it be per-client on mobile? Otherwise
  switching projects on the phone moves the desktop.
- Monaco editor and the code-server iframe are effectively unusable on mobile —
  mobile is view-only for code, with no editing promise.
- No frontend test framework exists; verification is `eslint` + `vite build`
  plus manual testing via DevTools device mode / PWA. The backend is unchanged
  (no API changes).

## 8. Verification (per phase)

```bash
npm run lint --prefix web && npm run build --prefix web
pytest   # confirm the backend still passes (no API changes)
```
