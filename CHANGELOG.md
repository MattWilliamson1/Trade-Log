# Changelog

What changed in each version pushed to users, newest first. Every push that
bumps `VERSION` must add a `## <version>` section here with at least one
bullet: CI refuses the push otherwise, and the in-app update prompt shows
these bullets to anyone updating. Entries before 2026-09-24 were rebuilt
from the commit history.

## 2026-09-24
- Reconcile open positions against your broker (Broker Sync → Reconcile Open Positions): pulls positions live from Schwab or IB, or from a positions CSV from any broker, treats the broker as correct, and lists the adds, closes and size fixes that make the log match
- Reconcile also catches a buy and a sell on the same contract both left open (a same-day close imported as a new short, say) and turns the later one into the earlier one's exit; IB corporate-action lines like AC.ODD are matched to their stock
- IB 'Today's Trades' import no longer logs a sell of shares bought on an earlier day as a new short: each fill is matched against what the log already holds, closes those trades oldest first, and the preview shows exactly what Import will do. Fetching again later skips fills already imported
- Close several positions at once, or a whole option spread in one go (Trading Log → Close Several Positions / Whole Spreads), with live-price and expired-option pre-fills and a net spread price
- Show what changed in each version: the update prompt lists what's new, and the full changelog is in the sidebar

## 2026-09-22.2
- Fix equity-curve drawdown, CAGR on a wiped-out account, and imported fees

## 2026-09-22.1
- Show the trail amount when switching a trade to a trailing stop

## 2026-09-22
- Add a database import with an explicit overwrite warning

## 2026-09-21.2
- Let the Trade Log headers importer carry currency, FX, exchange and fees

## 2026-09-21.1
- Keep the consolidation result on screen until acknowledged

## 2026-09-21
- Add scale-in/scale-out finder that consolidates split positions
- Move Mac launcher venv to ~/.tradelog and reinstall deps on requirements change

## 2026-09-11.2
- Read currency and transaction number from imported CSVs

## 2026-09-11.1
- Fetch a missing module on startup so the CSV importer reaches every install

## 2026-09-11
- Price non-US holdings in USD, and type in the trade's own currency
- Add a tolerant CSV importer that maps unfamiliar exports
- Let a stop be moved from the Open Positions panel
- Stop dropping columns the user selected
- Repair dead sidebar CSS, and make the update prompt look like one
- Clearer labels, a visible filter panel, and a closing confirmation
- Reject an exit date that falls before its entry date
- Ship csv_smart.py through the updater, and pick up new files in the same round

## 2026-08-27
- Add non-US listings, date-format choice, richer review PDF, real-data demo
- Add an opt-in compact layout

## 2026-08-24
- Diagnose Fidelity statements that yield no text

## 2026-08-19
- Harden migration runner against duplicate-column errors
- Rebuild demo data on a normalized-risk model
- Add sector pie metrics, GBP, and per-trade currency on both sides of a trade

## 2026-07-28
- Fix Mac/Windows installer: force cryptography wheel instead of source build

## 2026-07-27.2
- Show empty-state message instead of crashing on a zero-row trade view

## 2026-07-27.1
- Fix empty-view crash on trade log after CSV import (empty-DataFrame apply gotcha)

## 2026-07-02.2
- Fix leftover launch.bat after relocation; forward to per-user install

## 2026-07-02.1
- Force uv copy-mode so installs survive cloud-synced folders
- Install to per-user folder; make Mac app reliably launchable
- Add Fidelity statement PDF import
- Mark Fidelity statement import as beta in the UI
- Ship Fidelity import: bundle module, add pdfplumber, bump VERSION

## 2026-06-19.1
- Fix app failing to start: ship schwab_client.py with builds + updater

## 2026-06-19
- Add chart MRSI + variable EMA, fractional shares, partial-exit fix; ship Schwab sync; clean up release pipeline

## 2026-06-18
- Fix partial-fill handling: free-port launcher and IB execution aggregation
- Onboarding setup tour + installer launch UX (#4)
- Add sidebar Glossary; pin reportlab dependency
- Make demo trade data logically consistent
- Move Glossary from sidebar dropdown to its own main-area page
- Add volume panel to the Trade Log trade chart
- Add 20/50/150/200 SMA overlays to the trade chart
- Collapse weekend gaps on the trade chart
- Mark entry/exit price on chart; move Notes into main Add Trade form
- Highlight required Add Trade fields in a green box
- Make trade chart, buttons, and expander headers follow the active theme
- Theme section headings, number steppers, and file uploader
- Theme form-submit buttons and chart text on light themes
- Match data tables to theme via launch-time base + auto-restart on theme flip
- Fix restart prompt crash: st.iframe height must be >= 1, not 0
- Make updates complete + actually deliverable: bump VERSION, ship launch.py

## 2026-05-27
- Release 2026-05-27: exchange column, Mac bundled-uv installer, launch fixes

## 2026-05-25
- Trade Log v1 with dev workflow
- Fix live prices, spread net price, dropdown styling, stats 3-way P&L mode
- Add GitHub Actions auto-release and tracked installer assets
- Fix Actions release permissions
- Harden installer: OneDrive/ProgramFiles guards, venv cleanup, python.exe verification
- Fix database locked error: add WAL mode and 15s connection timeout
- Fix Select All error: apply selection before widget instantiation
- Equity curve: add date range filter and daily balance table
- Fix Styler.applymap -> map for pandas 2.1+
- Major feature expansion: equity stats, spread tagging, IB Flex cycle-split fix, UI polish
- Add cross-OS install test; gate release on test pass
- Add Mac release build; fix Windows launcher port
- launch.vbs: scan for free port starting at 8502
- Add in-app update checker and installer
