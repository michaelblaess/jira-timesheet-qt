# jira-timesheet-qt

<p align="center">
  <img src="docs/flags/gb.svg" height="13" alt=""> <b>English</b> ·
  <img src="docs/flags/de.svg" height="13" alt=""> <a href="README.de.md">Deutsch</a>
</p>

---

[![Stars](https://img.shields.io/github/stars/michaelblaess/jira-timesheet-qt?logo=github&logoColor=white&color=fbbf24)](https://github.com/michaelblaess/jira-timesheet-qt/stargazers)
[![Issues](https://img.shields.io/github/issues/michaelblaess/jira-timesheet-qt?logo=github&logoColor=white&color=f87171)](https://github.com/michaelblaess/jira-timesheet-qt/issues)
[![Last Commit](https://img.shields.io/github/last-commit/michaelblaess/jira-timesheet-qt?logo=git&logoColor=white&color=3b82f6)](https://github.com/michaelblaess/jira-timesheet-qt/commits/main)
[![License](https://img.shields.io/badge/license-Apache_2.0-3b82f6)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-3b82f6?logo=python&logoColor=white)](https://www.python.org/)
[![Qt](https://img.shields.io/badge/Qt-PySide6-41cd52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)

A native desktop application (PySide6 / Qt 6) for timesheets from Jira worklogs - including manual time entry for hours that are not booked in Jira.

<p align="center">
  <img src="docs/images/teaser.png" width="70%" alt="jira-timesheet-qt">
</p>

> **Disclaimer:** This project is **not** developed, supported, or authorized by Atlassian. "Jira" and "Atlassian" are registered trademarks of [Atlassian Corporation](https://www.atlassian.com/). This tool uses the public Jira REST API and is not affiliated with Atlassian.

## TUI or GUI?

This is the native desktop port of the Textual TUI
[jira-timesheet](https://github.com/michaelblaess/jira-timesheet). Both are built on the
**same code** - the same Jira integration, timesheet logic, manual time tracking, holiday
calendar and Excel/PDF export - so they produce identical results. Both run on **Windows,
macOS and Linux**. They differ in how you work with them, and each has genuine strengths:

- **[Terminal (TUI)](https://github.com/michaelblaess/jira-timesheet)** - runs in any
  terminal, **including over SSH**, and needs **no window manager** at all. That makes it the
  natural choice on a remote box or a headless Linux server where a desktop simply is not there.
  Keyboard-first, lightweight, retro-themed, and it does everything this GUI does.
- **Desktop (this app)** - native windows, menus and dialogs, mouse-driven throughout,
  columns you drag to resize, OS-native file and print dialogs. The comfortable choice when
  you are sitting at a desktop and prefer a windowed application.

Neither replaces the other - pick the one that fits your environment or your taste, or use
both. They keep their data in separate locations and run happily side by side.

## Screenshots

The application follows the light or dark theme and a configurable accent colour.

### List view - sortable, searchable, with day groups

<p align="center">
  <img src="docs/screenshots/main-dark.png" width="49%" alt="List view (dark)">
  <img src="docs/screenshots/main-light.png" width="49%" alt="List view (light)">
</p>

### Live search - filter by ticket or description, matches highlighted

<p align="center">
  <img src="docs/screenshots/search-dark.png" width="49%" alt="Search filter (dark)">
  <img src="docs/screenshots/search-light.png" width="49%" alt="Search filter (light)">
</p>

### Calendar and year view

<p align="center">
  <img src="docs/screenshots/calendar-dark.png" width="49%" alt="Calendar view (dark)">
  <img src="docs/screenshots/year-dark.png" width="49%" alt="Year view (dark)">
</p>

### My tickets - grouped by whose move it is

<p align="center">
  <img src="docs/screenshots/board-assigned-dark.png" width="49%" alt="My tickets (dark)">
  <img src="docs/screenshots/board-assigned-light.png" width="49%" alt="My tickets (light)">
</p>

### My activity - everything you had a hand in

<p align="center">
  <img src="docs/screenshots/board-relevant-dark.png" width="49%" alt="My activity (dark)">
  <img src="docs/screenshots/board-relevant-light.png" width="49%" alt="My activity (light)">
</p>

### Ticket details

<p align="center">
  <img src="docs/screenshots/detail-dark.png" width="55%" alt="Ticket details">
</p>

### Settings - Jira access with budget-field auto-detect

<p align="center">
  <img src="docs/screenshots/settings-dark.png" width="80%" alt="Settings - Jira access">
</p>

### Settings - status mapping for the ticket views

<p align="center">
  <img src="docs/screenshots/settings-tickets-light.png" width="80%" alt="Settings - ticket views">
</p>

## Features

- **Jira Cloud &amp; Data Center** - Worklogs via REST API; Jira Cloud (v3, basic auth with
  API token) by default, with a toggle for legacy Jira Server/Data Center (v2, bearer token)
- **Budget field auto-detect** - On Jira Cloud, one click finds the budget custom field
  automatically (no manual ID lookup)
- **List view** - Tabular with calendar week, weekday, day groups and target/actual hours;
  day totals coloured green above and red below the target
- **Live search / filter** - Filter by ticket ID or description as you type (`Ctrl+F`);
  matches are highlighted in the list
- **Resizable columns** - Drag the divider in the column header, widths are persisted;
  otherwise the description column fills the remaining width automatically
- **Manual time tracking** - Record time that is not booked in Jira via a dialog (`Ctrl+N`),
  edit it inline or from the context menu; stored in SQLite, colour-marked in the list, Excel
  and PDF
- **Configurable export columns** - Every column can be toggled for display and export
  independently and renamed for the export (settings page "Columns"), including a customer column
- **Calendar view** - Monthly grid with colour-coded day tiles; clickable ticket links open
  the detail dialog
- **Year view** - Twelve month tiles with progress bar, forecast, revenue totals and the top
  tickets per month; every ticket is a link to its detail dialog
- **Excel export** - Formatted timesheet with logo and signature line
- **PDF export** - Adobe-signable, Unicode font
- **Print preview** - Preview and print the timesheet straight from the app (`Ctrl+P`)
- **Public holidays** - German public holidays per federal state, gap detection
- **Target/actual &amp; forecast** - Working-time comparison with difference; yearly forecast
  with vacation days and a net/gross revenue projection (configurable hourly rate and VAT)
- **Ticket details** - A modal dialog shows status, type, assignee, components and a link to
  the ticket
- **Ticket analysis** - Turns any ticket into an interactive report: a true-to-scale timeline
  of its life cycle, waiting time per status (calendar time versus actual working hours), the
  people involved, key figures such as flow efficiency and first response, plus findings that
  each carry their evidence. The result is a single self-contained HTML file that works
  offline and can be shared (`Ctrl+T`) Unusually long waiting times are marked in red, related tickets show their title, and the finished report opens straight in the browser.
- **My tickets** - Every ticket assigned to you, grouped by whose move it is: mine, someone
  else's, backlog, handback, closing. Plus markers for what needs attention, the idle time in
  working days and three charts (inflow against outflow, stock, age distribution)
- **My activity** - Tickets you had a hand in even though they belong to someone else:
  commented, mentioned, edited or logged work on, within a configurable time window
- **My team** - The same view onto a colleague's tickets, without them having to install
  anything. You keep a short list of people in the settings; the search goes by **name** - one
  person may run several Jira accounts, and many accounts do not reveal their mail address at
  all. Deliberately **without charts**: throughput per month would be a performance metric
  about somebody else, and that is not what this is for
- **Pile of Shame** - Marks tickets whose status claims activity although there has been
  neither a change nor a logged hour since the threshold. The second half is the trick: a
  long-running ticket deliberately kept open, with regular bookings, stays out - no exception
  list needed
- **Anonymization** - Replace tickets, descriptions, authors, status names and the Jira host
  with dummy values for safe screenshots; the real data stays untouched
- **Docked log** - An attachable message panel with the full history (`Ctrl+L`)
- **Zoom** - Scale the whole interface with `Ctrl` +/- / 0 or `Ctrl` + mouse wheel, like a browser
- **Worklog cache** - Completed months are cached, the year view loads instantly
- **Bilingual UI** - German / English
- **Settings backup** - Every save writes a rolling backup and a golden copy; a lost Jira
  access can be restored on the next start

## Prerequisites

The program signs in to Jira with your own account - there is no server and no
sign-up. You need three things: the address of your Jira instance, a token and
your login. How you get the token depends on which Jira you have.

### Jira Cloud (address ends in `.atlassian.net`)

1. Open [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) and sign in.
2. Choose **Create API token**.
3. Give it a name you will recognise later.
4. Pick an expiry date - anything from 1 to 365 days, one year by default.
5. **Create**, then **Copy to clipboard**.

The token is shown **only once**. If you dismiss it, create a new one. Put it
straight into your password manager.

Atlassian offers tokens **with and without scopes**. Without scopes the token
has the same rights you have and will work in any case. With scopes it is more
tightly limited and therefore safer - you then need read access to Jira, or the
server answers with 401 or 403.

For the login, enter the **email address of your Atlassian account**, not your
display name.

Keep the expiry date in mind: after a year at the latest the fetch stops
working, and the error only says that authentication was refused. Create a new
token and enter it in the settings.

### Jira Data Center / Server

Avatar in the top right, then **Profile**, then **Personal access tokens** in
the left menu. This exists from Jira Core/Software 8.14 and Jira Service
Management 4.15 onwards.

Here the login is your **Jira username**, not your email address. And the
**Jira mode (legacy API)** switch in the settings has to be on - otherwise the
program talks to the Cloud endpoint, which does not exist here.

**ScriptRunner is required on Data Center.** The program looks up your work
logs through the JQL function `issueFunction in workLogged(...)`, which
ScriptRunner provides. Without the plugin Jira rejects the query as invalid
JQL. On Jira Cloud this does not apply - there the search goes through the
regular worklog endpoint.

### Budget field (optional)

If your instance has a custom field for budget, the program can carry it along
as a column.

On Cloud the **Auto-detect** button in the settings dialog (`Ctrl+,`) is enough. It queries
`/rest/api/3/field` and offers every field whose name contains "budget".

By hand it works anywhere: open `https://YOUR-INSTANCE/rest/api/3/field` in the
browser (Data Center: `/rest/api/2/field`), find the field name and take its
`id`. It looks like `customfield_12345`.

The field may stay empty. You then only lose that one column.

### Status values for the ticket views (optional)

The six status fields in the settings dialog (`Ctrl+,`) start out empty. You find your own
status names on any Jira issue at the top, or as the column titles of your
board - enter them comma-separated, spelled exactly as they are there.

Leaving them empty is fine: the program then sorts by the status category Jira
assigns itself (to do, in progress, done). The views work, they just lack the
finer distinction - between "waiting for approval" and "my turn", for instance.

## Installation

### One-click install

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/michaelblaess/jira-timesheet-qt/main/install.ps1 | iex
```

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/michaelblaess/jira-timesheet-qt/main/install.sh | bash
```

### Download

Prefer a file? Grab the latest archive from the
[Releases](https://github.com/michaelblaess/jira-timesheet-qt/releases) page, unpack it and
start the application. It runs on **Windows, macOS and Linux**.

## Usage

```bash
jira-timesheet-qt              # start the application
jira-timesheet-qt --demo       # start with example data, no Jira access required
```

On first start, open the settings (`Ctrl+,`) and configure the **Jira access** - where
token and field ID come from is covered under [Prerequisites](#prerequisites):

- **Jira host URL** - Cloud: the canonical `https://your-company.atlassian.net`
- **Email / login** - Cloud: your Atlassian login email; Data Center: your Jira username
- **Token** - Cloud: an API token from
  [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens);
  Data Center: a bearer token (PAT)
- **Jira mode** - leave off for Jira Cloud, enable for a legacy Server/Data Center
- **Budget field** - on Cloud, use **Auto-detect** to fill in the custom field automatically
- **Federal state** - for the public-holiday calculation

Then press `F5` to fetch the bookings for the selected month.

### Recording time that is not in Jira

Not every hour ends up as a worklog in Jira. `Ctrl+N` opens a dialog for date, ticket,
description, customer and effort. The effort may be written the way you note it anyway:
`3h 30m`, `3:30`, `3.5` or `45m`.

These entries live in their own SQLite file (`~/.jira-timesheet-qt/manual-entries.db`) and
**never** in the Jira cache. They count everywhere - daily total, monthly total, target/actual,
calendar, year view, Excel and PDF - and are colour-marked so it is obvious what comes from
Jira and what does not. A right-click on a row opens a context menu; description and effort of
a manual entry can be edited directly in the table.

### Setting up the ticket views

The **My tickets**, **My activity** and **My team** tabs load on their own the first time you look at
them, and `F5` fetches them again. Neither groups by status name. They group by the question
**whose move is it**. Because every Jira instance names its statuses differently, that mapping
has to be entered once: Settings (`Ctrl+,`), page **Tickets**.

If the fields stay empty, the application falls back to Jira's own status category. That works
right away but is coarse - Jira only knows "new", "in progress" and "done".

| Group | What belongs there | Example |
| --- | --- | --- |
| Mine | The ball is in your court, work is happening | `In Progress, In Review` |
| Backlog | Refined and ready to be pulled | `Ready, Planned` |
| Someone else's | Waiting for approval by another person - this is where you chase | `Waiting for approval` |
| Live, awaiting test | Deployed to production, still needs to be tested there | `Delivered, For assessment` |
| Handover | Statuses Jira counts as **done** although the ticket is still waiting to go live | `For handover, Deployment pending` |
| Done | Truly finished - a plain check, no action needed and no threshold | `Resolved, Closed` |

**The "handover" field matters most.** A status like "Deployment pending" or "For handover"
sits in Jira's *Done* category. Such tickets slip through every ordinary filter and without
this entry they are **never even queried** - they are simply missing, and nothing says so.

**Live, awaiting test** has a special rule: if the reporter is somebody else, the ticket should be handed
back rather than worked on. If you are the reporter yourself, there is nobody to hand it back
to, so it moves to "Mine" instead of gathering dust in a group labelled "do not work on this".

The **priorities** are a ranking, most urgent first. It drives the sort order inside a group
and decides which tickets get the *priority* marker. Bugs always come first regardless.

#### Markers

A ticket can carry several at once - which is why they are markers and not more groups. A
drawer could file each ticket only once.

| Marker | Meaning |
| --- | --- |
| Pile of Shame | The status claims activity, but there has been neither a change nor a logged hour since the threshold |
| Handback | Live, foreign reporter - the test is theirs, not yours |
| Stale | Untouched for a very long time (default: 180 days) |
| Priority | Priority within the upper part of the ranking |
| Chase | Waiting for approval by somebody else |
| Blocked | A predecessor is still open |

#### Thresholds and time window

| Setting | What for | Default |
| --- | --- | --- |
| Time window | Only for "My activity". 0 = no window, which turns the list into an archive instead of a work stock | 90 days |
| Stale after | When the *stale* marker is set | 180 days |
| Threshold: mine | Working days until the Pile of Shame in your own group | 20 |
| Threshold: others | The same for tickets waiting for approval | 10 |
| Threshold: closing | The same for the closing group. 0 exempts the role | 0 |

These numbers are a **choice, not a measurement**. Set too low, the marker hits everything and
then says nothing - pick a threshold that leaves a handful of tickets, not half the list.

The maths runs in **working days** (Mon-Fri, 8 am to 6 pm), not calendar days. A ticket sitting
over a long weekend has not been neglected for three days.

### Setting up "My team"

The **My team** tab shows a colleague's tickets - same grouping as your own, just from their
point of view. Who shows up there is kept in a short list: settings (`Ctrl+,`), page
**My team**.

The search goes by **name**, not by mail address. That is not a stylistic choice but a
measurement: in a real instance, an account that did expose its address held zero tickets,
while a second account of the same person, without a visible address, held a hundred and
twenty. Not readable does not mean not there - it is a question of profile visibility.

The result list shows open tickets and last contact per account, most recently used first.
**The date decides which account is current, not the count**: in that same measurement the
active account carried two tickets and a retired one eighteen. If a person runs several
accounts, select them all with `Ctrl` and take them over as one person. An account found later
goes in under the same display name.

Deliberately left out: **the charts**. They show throughput per month, which about another
person would be a performance metric. Worklog timestamps are not even requested for foreign
tickets, so no Pile of Shame appears there either. The yardstick is simple: whatever the Jira
board shows anyway, this view may show too.

### Anonymizing for screenshots

*View → Anonymize data* (also on the toolbar) replaces tickets, descriptions, authors and the
Jira host with neutral dummy values across every view and the log. Your real data stays in the
cache and returns the moment you switch it off - handy for screenshots and demos.

## Liability notice on first start

On its first start the program shows a notice that has to be confirmed - without your consent it exits. The reason: this tool reads work log entries from a third-party system through the Jira REST API. Which issues and work logs become visible is determined solely by the permissions of the account you use, and depending on how rights are assigned these may include entries booked by other people. By confirming, you declare that you will only use the program against Jira instances you are authorised to access, and that you will only evaluate data you are permitted to process.

Your consent is recorded in `~/.jira-timesheet-qt/disclaimer.json` and is only requested again when the wording changes. The "Storage" tab of the settings dialog shows the location, where you can also delete the file to see the notice again.

The software is provided free of charge and without warranty of any kind ("as is"), as set out in section 7 of the Apache License 2.0. The liability of the author (Michael Blaess) for damages arising from its use is excluded to the extent permitted by applicable law. Liability for intent and gross negligence, for injury to life, body or health, and under mandatory product liability law remains unaffected.

## Keyboard Shortcuts

| Key | Action |
| --- | --- |
| `F5` | Fetch the bookings for the month (or the year in year view) |
| `Ctrl+F` | Focus the search field |
| `Ctrl+N` | Record manual time |
| `Ctrl+D` | Show ticket details |
| `Ctrl+T` | Ticket analysis (interactive report as an HTML file) |
| `Ctrl+E` | Excel export |
| `Ctrl+Shift+E` | PDF export |
| `Ctrl+P` | Print preview |
| `Ctrl+L` | Show / hide the log panel |
| `Ctrl` +/- / 0 | Zoom in / out / reset (also `Ctrl` + mouse wheel) |
| `Ctrl+,` | Settings |
| `F1` | Info |
| `Ctrl+Q` | Quit |

## Configuration

Settings are stored in `~/.jira-timesheet-qt/settings.json`:

| Setting | Description | Default |
| --- | --- | --- |
| Jira host | URL of the Jira instance (Cloud: `...atlassian.net`) | - |
| Token | API token (Cloud) or bearer token (Data Center) | - |
| Email | Atlassian login (Cloud) or Jira username (Data Center) | - |
| Jira mode (legacy API) | Off = Jira Cloud (v3), on = Data Center (v2) | off |
| Budget custom field | Custom field ID; Cloud supports **Auto-detect** | customfield_... |
| Federal state | For the public-holiday calculation | SN |
| Target hours/day | Working hours per day | 8.0 |
| Max. yearly hours | Upper limit for the progress bar | 1720 |
| Vacation days | For the yearly forecast | 30 |
| Hourly rate | Net, for the revenue projection | 0 (off) |
| VAT rate | Percent, for the gross calculation | 19 |
| Target hours in export | Shows the target row in Excel/PDF | false |
| Ticket links in export | Hyperlinks in Excel/PDF | false |
| Default customer | Customer for all entries fetched from Jira | Vertrieb |
| Highlight manual entries | Colours manual time in list, Excel and PDF | true |
| Day-total colouring | Colours daily totals by target/actual | true |
| Columns | Per column: display, export and label | all enabled |
| Status "mine" | Status names for your own working group | empty |
| Status "backlog" | Status names for the work stock | empty |
| Status "someone else's" | Status names for tickets in other hands | empty |
| Status "handback" | Status names for delivered tickets awaiting assessment | empty |
| Status "closing open" | Statuses Jira counts as done but with work remaining | empty |
| Priorities | Ranking, most urgent first | empty (Jira order) |
| Time window | Look-back for "My activity" | 90 days |
| Stale after | Threshold for the *stale* marker | 180 days |
| Pile of Shame thresholds | Working days per group, 0 disables | 20 / 10 / 0 |
| Theme / accent / zoom | Appearance | system / orange / 100 % |
| Language | UI language (de / en) | de |

## Relationship to the Textual version

The code (`models/`, `services/`, `i18n.py`) is **copied**, not imported, from
[jira-timesheet](https://github.com/michaelblaess/jira-timesheet) - a change there does not
arrive here automatically. That is deliberate: importing it would pull the whole TUI framework
into this app. To keep the two cores from drifting apart unnoticed:

```bash
uv run poe core-sync      # compares both cores and reports differences
```

Both applications keep their files in separate locations
(`~/.jira-timesheet-qt` vs. `~/.jira-timesheet`), so they can be used in parallel.

## Tech Stack

- [Python](https://python.org) >= 3.12
- [PySide6](https://doc.qt.io/qtforpython/) - Qt 6 bindings (LGPL)
- [qtawesome](https://github.com/spyder-ide/qtawesome) - Material Design icons
- [httpx](https://www.python-httpx.org) - async HTTP client
- [openpyxl](https://openpyxl.readthedocs.io) - Excel export
- [fpdf2](https://py-pdf.github.io/fpdf2) - PDF export
- [holidays](https://python-holidays.readthedocs.io) - public-holiday calculation

## Development

Setting up the development environment (this is for contributors, not for installing the app):

```bash
git clone https://github.com/michaelblaess/jira-timesheet-qt.git
cd jira-timesheet-qt
./bootstrap.ps1        # set up the dev environment with uv (Linux/macOS: ./bootstrap.sh)
uv run poe run         # run from source
uv run poe test        # run the test suite
uv run poe lint        # ruff + mypy (strict)
```

## License

Apache License 2.0, see [LICENSE](LICENSE).

---

> **Trademark Notice:** "Jira" is a registered trademark of
> [Atlassian Corporation](https://www.atlassian.com/). This project is not affiliated with,
> endorsed by, or sponsored by Atlassian.
