# Trade Log

A personal trading journal and portfolio tracker built with Python and Streamlit. Runs entirely on your own computer — your data never leaves your machine.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Running the App](#running-the-app)
5. [First-Time Setup](#first-time-setup)
6. [Page-by-Page Guide](#page-by-page-guide)
   - [Trading Log](#-trading-log)
   - [Trading Plan](#-trading-plan)
   - [Statistics](#-statistics)
   - [Equity Curve](#-equity-curve)
   - [Trading Tools](#-trading-tools)
   - [Tags](#-tags)
   - [Broker Sync — Interactive Brokers Setup](#-broker-sync)
   - [Settings](#-settings)
7. [Email Alerts for Earnings — Step-by-Step](#email-alerts-for-earnings)
8. [IB Flex Query Setup — Step-by-Step](#ib-flex-query-setup)
9. [Troubleshooting](#troubleshooting)

---

## What It Does

Trade Log is a self-hosted trading journal. You log trades manually or import them directly from Interactive Brokers. The app tracks your open positions with live prices, calculates P&L, monitors stop distances and position sizes, plots your equity curve, and emails you when open positions have upcoming earnings dates.

**Key features:**
- Stocks, options (including multi-leg spreads), and futures
- Live prices via Yahoo Finance or Interactive Brokers TWS/Gateway
- Import trades and account history directly from Interactive Brokers via Flex Query
- Equity curve with Time-Weighted Return (TWR) chart
- Earnings date tracking with automated email alerts
- Statistics dashboard with win rate, average win/loss, Sharpe & Sortino ratios
- Position sizing calculators
- Demo Mode / Live Mode toggle so you can test safely before going live

---

## Requirements

- **Windows 10 or 11** (macOS is also supported — see `build_mac_distribution.py`)
- **Python 3.10 or newer** — download free from [python.org](https://www.python.org/downloads/)
  - During installation, tick **"Add Python to PATH"** — this is important
- An internet connection (for live prices and earnings data)

---

## Installation

**If you received the installer package**, just double-click `INSTALL - Double-Click This First.bat` and follow the prompts. Skip to [Running the App](#running-the-app).

**If you are setting up from source:**

1. Open a terminal (press `Win + R`, type `cmd`, press Enter)
2. Navigate to the Trade Log folder:
   ```
   cd "C:\path\to\Trade Log"
   ```
3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
   > **Note:** `ib_insync` and `nest_asyncio` are only needed for live IB connection (TWS/Gateway). The Flex Query feature (which fetches data over the internet without TWS) works without them. If the install fails on those two packages, you can safely remove them from `requirements.txt` and reinstall — everything except the live TWS connection will still work.

---

## Running the App

**Using the launcher (recommended):**
Double-click `launch.bat` in the Trade Log folder.

**From the terminal:**
```
python -m streamlit run app.py
```

The app opens automatically in your web browser at `http://localhost:8502`. Leave the terminal window open while you use the app — closing it stops the app.

---

## First-Time Setup

When you first open the app, do the following in order:

1. **Set your account balance** → go to ⚙️ Settings → Account & Equity → enter your current account value → Save.
2. **Choose Demo or Live Mode** → ⚙️ Settings → App Mode section. Start in **Demo Mode** until you are comfortable, then switch to Live.
3. **Configure email alerts (optional but recommended)** → see [Email Alerts for Earnings](#email-alerts-for-earnings) below.
4. **Connect Interactive Brokers (optional)** → see [IB Flex Query Setup](#ib-flex-query-setup) below.

---

## Page-by-Page Guide

---

### 📋 Trading Log

This is the main page. It shows all your trades in a table and lets you add, edit, and delete them.

#### Ticker Lookup
Type any stock symbol in the search box at the top to instantly see the company name and exchange. Useful for confirming you have the right symbol before logging a trade.

#### Adding a Trade
Click **➕ Add Trade** to expand the entry form.

1. **Instrument Type** — choose Stock, Option, or Future at the top. For options and futures you can add multiple legs at once using the "Legs" counter.
2. **Ticker / Underlying** — type the symbol. A live price appears automatically so you can double-check before entering.
3. **Trailing Stop** — tick this checkbox (stocks only) to set a trailing stop instead of a fixed one. Choose the trail unit ($ or %) and the trail amount.
4. Fill in Entry Date, Quantity, Entry Price. Exit Date and Exit Price are optional — leave them blank for open positions.
5. **Stop Loss** — enter a stop price. The "Opening Stop" is locked in at entry and never changes; the "Current Stop" can be updated as the trade develops.
6. **Tags** — assign one or more tags to categorise the trade (e.g. "Earnings Play", "Swing", "Sector Rotation").
7. **Notes / Chart Notes** — free-text fields. Notes appears in the table; Chart Notes is separate for your chart markups.
8. Press **Ctrl+Enter** or click **Add Trade** to save.

#### The Trade Table
The table shows all your trades. You can customise which columns appear using the **Columns** multiselect above the table.

- **Column presets** — choose "Stocks" or "Options" for a sensible default set of columns.
- **Filters** — filter by Status (Open / Closed), Instrument type, Ticker, Tags, Side, and Date range.
- **Sorting** — click any column header to sort.
- **Live Price** — click **⚡ REFRESH LIVE PRICES** in the sidebar to fetch current prices. Prices do not auto-refresh to avoid rate limits.
- **Color coding** — rows or text can be colored green/red based on whether a position is in profit or loss. Configure this in ⚙️ Settings.

**Key columns explained:**
| Column | What it shows |
|---|---|
| P&L | Unrealised P&L for open trades, realised P&L for closed trades |
| Open Risk | Current dollar risk (position size × distance to stop) |
| Opening Risk | Dollar risk calculated at the time of entry |
| % of Account | Position value as a % of your account. Turns yellow/red when thresholds are exceeded |
| Stop Dist | How far the current price is from the stop. Turns yellow/red near the stop |
| Days in Trade | Calendar days the position has been open |
| Ann. Return % | Annualised % return based on days held |
| Earnings | Next earnings date for the underlying (auto-fetched from Yahoo Finance) |

#### Spread Summaries (Options)
When you have option trades that share the same underlying and expiration, the app automatically groups them as a spread and shows a **Spread Summaries** section below the main table. This displays combined P&L, net delta, net theta, and DTE across all legs. Click a spread to expand the detail view.

#### Editing a Trade
Scroll down to the **✏️ Edit Trade** expander. Select the trade you want to edit from the dropdown, make your changes, and click **Save Changes**.

- You can update the exit date/price to close a trade.
- Earnings date can be manually overridden if the auto-fetched date is wrong.
- For options, you can update the strike, expiration, multiplier, and underlying price at entry.

#### Deleting a Trade
Use the **🗑️ Delete Trade** expander. Select the trade and confirm deletion. This is permanent.

#### Attachments
Each trade has an attachments section in the Edit panel. Attach chart screenshots, trade plans, or any files you want to associate with the trade.

#### Importing Trades
Use the **📥 Import** tab to bulk-import trades from a CSV file or directly from Interactive Brokers via Flex Query. The CSV format requires columns: `entry_date`, `ticker`, `quantity`, `entry_price` — see `tradeImport.csv` for an example.

---

### 📝 Trading Plan

A structured template for planning a trade before you take it. Fill in:

- **Ticker and Sentiment** (Bullish / Bearish / Neutral)
- **Rationale, Fundamentals, Technicals** — text boxes for your analysis
- **Trade Type** (Swing / Momentum / Options Play, etc.)
- **Hold Time** — your expected holding period
- **Entry Signal and Confirmation criteria**
- **Entry Price, Profit Target, Stop Loss** — the app calculates your Risk/Reward ratio automatically
- **Attachments** — attach chart images to the plan

Saved plans are listed below the form. You can review, delete, or use them as a reference after you enter the trade.

---

### 📊 Statistics

A performance dashboard for your closed (and optionally open) trades.

#### Filters
At the top, filter by:
- **Instrument** — All, Stocks, Options, or Futures
- **Ticker** — narrow to specific symbols
- **Status** — Closed only (default), All, or Open only
- **Tags** — filter to trades with specific tags
- **Date range** — use the quick buttons (YTD, MTD, 30 Days, 7 Days, All Time) or set a custom range

#### Display Options
- **% Returns** — toggle to show all return metrics as percentages rather than dollar amounts
- **Mean Method** — choose between simple Mean or 10% Trimmed Mean (trims outlier trades for a more representative average)
- **Net of Commission** — toggle to subtract commissions from all P&L calculations

#### What's Shown

**Summary metrics:** Total trades, win rate, gross P&L, net P&L after commission, average win, average loss, profit factor (gross wins ÷ gross losses), Sharpe ratio, Sortino ratio, and max drawdown.

**Charts:**
- P&L over time (bar chart, by trade or by month)
- Win/Loss distribution histogram
- Cumulative P&L curve
- Best and worst trades
- Performance breakdown by tag

---

### 📈 Equity Curve

Tracks your account balance over time and plots it as a chart. Requires you to enter or import daily ending balances.

#### Chart Tab
- **View toggle** — switch between **% Return (TWR)** (default) and **Balance ($)**
- **TWR (Time-Weighted Return)** — the % return strips out the effect of deposits and withdrawals, showing your actual investment performance
- **Benchmarks** — overlay SPY, QQQ, IWM, LQD, or JNK for comparison. In TWR mode, benchmarks are also shown as % return from the same start date
- **20-Day Moving Average** — plotted as a dotted line on the chart

**Summary metrics below the chart:**
- Current Balance
- TWR (total time-weighted return since first entry)
- Net Contributions (total deposits minus withdrawals)
- Max Drawdown (largest peak-to-trough drop in the TWR series)

#### Manual Entry Tab
Add a single day's balance manually. Enter the date, end-of-day balance, any contributions (deposits) that day, and any withdrawals. This is all you need for the basic equity curve.

#### Import Tab
Bulk-import balance history from a CSV file. Useful if you have historical data in a spreadsheet. Required columns: `date`, `balance`. Optional: `contributions`, `withdrawals`.

#### IB Flex Import Tab
Import your complete balance history directly from Interactive Brokers. This is the most accurate and convenient method. See [IB Flex Query Setup](#ib-flex-query-setup) for how to configure this. Once set up:
1. Select the date range you want to import
2. Click **📥 Fetch Balance History**
3. Review the preview table
4. Click **✅ Import** to save to the database
5. The chart may take a moment to populate after importing

---

### 🛠️ Trading Tools

A set of calculators that do not require any saved data.

#### ATR Calculator
Calculates the Average True Range for any ticker over a chosen lookback period. The result auto-fills into the Stop Calculator below if you use ATR-based stops.

#### Stop Calculator
Calculates a stop price from an entry price. Two modes:
- **% Stop** — enter your stop percentage, get the stop price and dollar distance
- **ATR Stop** — enter (or use the auto-filled) ATR and a multiplier (e.g. 1.5× ATR). The stop price auto-fills into the Share Count calculators below.

#### Share Count — Max Loss Based
Answers: *"Given my maximum acceptable loss, how many shares can I buy?"*
- Enter account size, maximum loss ($ or % of account), entry price, and stop price
- Returns: number of shares, dollar risk, position value, and % of account

#### Share Count — Allocation Based
Answers: *"If I allocate X% of my account, how many shares is that?"*
- Enter account size, allocation amount ($ or % of portfolio), and entry price
- Optionally enter a stop price to see the dollar risk and risk % that allocation implies

#### R-Multiple Calculator
Converts P&L into R-multiples (units of initial risk). Enter your initial risk ($ per share) and the trade P&L to see how many R the trade returned. Useful for measuring trade quality independent of position size.

#### Break-Even Calculator
For options traders — enter the premium paid, strike price, and option type (call/put) to calculate the break-even price at expiration.

---

### 🏷️ Tags

Manage the tags used to categorise trades. Tags let you filter and group trades in the Trading Log and Statistics pages.

- **Add a tag** — enter a name and optional description, click Add
- **Delete a tag** — click the delete button next to any tag. This removes the tag from all trades that use it

Examples of useful tags: `Earnings Play`, `Breakout`, `Mean Reversion`, `Swing`, `Options Income`, `High Conviction`, `Speculative`

---

### 🔗 Broker Sync

Connects the app to Interactive Brokers for live prices, account balance sync, and trade import.

There are two independent connection methods. You do not need both — most users only need the Flex Query method.

| Method | What it does | Requires |
|---|---|---|
| **TWS / Gateway (Live)** | Real-time prices, live account balance | IB TWS or Gateway running on your computer |
| **Flex Query (HTTP)** | Historical balance, deposits/withdrawals, trade history | Internet connection only — no TWS needed |

#### TWS / Gateway Connection

This requires Interactive Brokers Trader Workstation (TWS) or IB Gateway to be running on your computer at the same time as Trade Log.

**Settings:**
- **Host**: `127.0.0.1` (leave this unless TWS is on a different computer)
- **Port**: `7497` for paper trading via TWS, `7496` for live via TWS, `4002` for paper via Gateway, `4001` for live via Gateway
- **Client ID**: `1` (leave as default unless you have multiple apps connecting)
- **Use IB live prices**: tick this to use IB prices instead of Yahoo Finance
- **Auto-sync balance on startup**: tick to update your account balance from IB each time the app loads
- **Auto-connect on startup**: tick to attempt connection automatically when the app loads

Click **Test Connection** to verify TWS/Gateway is reachable.

> **TWS API must be enabled.** In TWS: Edit → Global Configuration → API → Settings → tick "Enable ActiveX and Socket Clients", set Socket port to match the port above.

#### Flex Query

The Flex Query method fetches data directly from IB's servers over the internet. No TWS required. See [IB Flex Query Setup](#ib-flex-query-setup) for the full setup guide.

Once your token and query ID are saved here, use the **📥 Fetch via Flex Query** button to pull your latest data, or upload an XML file directly.

---

### ⚙️ Settings

#### Display
- **Euro dates** — toggle to show dates as DD/MM/YYYY instead of MM/DD/YYYY

#### Row Color Coding
Optionally color-code trade rows based on status and P&L direction:
- Choose **Text color** (only the text changes color) or **Row background** (the entire row is highlighted)
- Pick your colors for Open-Profit, Open-Loss, Closed-Profit, and Closed-Loss

#### Multi-Currency
If your account is in a non-USD currency (AUD, CAD, EUR), enable this to see P&L figures converted to your native currency alongside the USD figures. FX rates are fetched from Yahoo Finance.

#### Account & Equity
- **Account Balance** — your current total account value. Used for "% of Account" calculations and risk metrics.
- **Starting Equity** — used as the baseline for equity curve normalisation.
- **Starting Date** — optionally pin the equity curve to a specific start date.

#### Alert Thresholds
- **% of Account thresholds** — the % of account at which a position turns yellow (warning) and red (danger) in the trade table
- **Distance from Stop thresholds** — how close the current price has to be to the stop before the cell turns yellow or red. Set the unit (%, $, or ATR multiples)

#### App Mode
- **Demo Mode** — auto-sync and auto-connect features are disabled. All manual actions still work. Safe for testing.
- **Live Mode** — enables auto-sync and auto-connect on startup.

#### Commission Defaults
Default commission amounts pre-filled when adding trades:
- Stocks: flat fee per trade (e.g. $0 for IB, $4.95 for others)
- Options: per contract (e.g. $0.65)
- Futures: per contract (e.g. $2.25)

#### Email Alerts
See the full guide below.

---

## Email Alerts for Earnings

The app can email you automatically when any open position has an upcoming earnings date. This is configured in ⚙️ Settings → Email Alerts.

### How it works

- Each night (or whenever triggered), the app checks all open positions for upcoming earnings
- If an earnings date is within your threshold (default: 5 trading days), it sends you an email listing the affected positions
- Earnings dates are fetched automatically from Yahoo Finance. You can also override the date manually in the Edit Trade panel.

### Step 1 — Choose an email provider

The app uses SMTP to send emails. You need an outgoing mail server. The easiest option is a **Gmail account with an App Password**. This is free and takes about 5 minutes to set up.

> **Why an App Password?** Google does not allow apps to log in with your regular password. An App Password is a separate 16-character password generated specifically for this app. It only works for sending email — it cannot access your Google account in any other way.

### Step 2 — Create a Gmail App Password

1. Go to [myaccount.google.com](https://myaccount.google.com) and sign in
2. Click **Security** in the left menu
3. Under "How you sign in to Google", click **2-Step Verification** and make sure it is turned on (you must have 2-Step Verification enabled to create App Passwords)
4. Go back to Security, scroll down and click **App Passwords** (if you do not see it, search for "App Passwords" in the search bar at the top of the page)
5. In the "App name" box, type `Trade Log` (you can type anything — this is just a label for your own reference)
6. Click **Create**
7. Google shows you a 16-character password like `abcd efgh ijkl mnop` — **copy it now** (you will only see it once). Remove the spaces when you paste it into the app.

### Step 3 — Enter the settings in Trade Log

In Trade Log, go to ⚙️ Settings → Email Alerts section and fill in:

| Field | Value |
|---|---|
| SMTP Host | `smtp.gmail.com` |
| Port | `587` |
| SMTP Username | Your full Gmail address (e.g. `yourname@gmail.com`) |
| SMTP Password | The 16-character App Password from Step 2 (no spaces) |
| Send Alerts To | The email address you want alerts sent to (can be the same Gmail or a different address) |
| Alert threshold | Number of **trading days** before earnings to trigger an alert. Default is 5 (one trading week). |

Click **💾 Save Email Settings**.

### Step 4 — Send a test email

Click **📧 Send Test Email**. Within a minute you should receive a test message at the address you entered. If it does not arrive, check your spam folder first, then see [Troubleshooting](#troubleshooting).

### Step 5 — Check earnings now (optional)

Click **📬 Check Earnings & Send Alerts Now** to immediately scan all open positions and send alerts for any that have earnings within your threshold. This is the same check that runs automatically.

### Using a different email provider

If you do not want to use Gmail, any SMTP-capable email service works. Common settings:

| Provider | SMTP Host | Port |
|---|---|---|
| Gmail | smtp.gmail.com | 587 |
| Outlook / Hotmail | smtp-mail.outlook.com | 587 |
| Yahoo Mail | smtp.mail.yahoo.com | 587 |
| Apple iCloud | smtp.mail.me.com | 587 |

For Outlook and Yahoo, you also need to generate an App Password in your account security settings — the process is similar to Gmail.

---

## IB Flex Query Setup

The Flex Query connects Trade Log to Interactive Brokers over the internet and pulls your account balance history, cash transactions, and trade history. **No TWS or IB Gateway needs to be running** — this works even when the market is closed.

This section walks through the complete setup in plain English.

---

### Part 1 — Create the Flex Query in IB

**Step 1: Log in to IB Account Management**

Go to [interactivebrokers.com](https://www.interactivebrokers.com) → Log In → select **Account Management** (not TWS).

---

**Step 2: Navigate to Flex Queries**

In the left menu: **Reports** → **Flex Queries**

You will see two sections: "Activity Flex Query" and "Trade Confirmation Flex Query". You want **Activity Flex Query**. Click **Create** (or the + icon).

---

**Step 3: Name your query**

Give it a name you will recognise, like `Trade Log Export`. This name appears in the app.

---

**Step 4: Select the sections (data to include)**

This is the most important step. You need to enable specific sections for the app to work correctly.

Under **Select Sections**, enable the following:

**Required for equity curve:**
- ✅ **Change in NAV** — tick this section. Under Options, select **Mark-to-Market**. Make sure **Ending Value** is included in the field list (it usually is by default).

**Required for cash transactions (deposits/withdrawals):**
- ✅ **Cash Transactions** — tick this section. Under Options, select both **Detail** and **Summary** (the app filters out duplicates automatically). Make sure **Amount**, **Type**, **Report Date**, and **Description** are included.

**Optional but useful:**
- ✅ **Trades** — tick this if you want to import trades from IB into Trade Log. Under Options, select **Execution** and **Closed Lots**.

---

**Step 5: Configure the delivery settings**

Scroll down to **Delivery Configuration**:
- **Format**: `XML`
- **Period**: `Last 365 Calendar Days` (or whatever range you need — longer periods mean more data)

Click **Save** (or **Create**).

---

**Step 6: Note your Query ID**

After saving, IB shows your list of Flex Queries. Find your new query and look for the **Query ID** — it is a number like `1512513`. Write this down.

---

### Part 2 — Generate a Flex Token

The Flex Token is a password that allows Trade Log to fetch your reports. It is separate from your IB login password.

**Step 1:** In IB Account Management, go to **Reports** → **Flex Queries**

**Step 2:** At the top of the Flex Queries page, click **Manage Tokens** (or look for a link called **Create/Manage Tokens** or **Configure Flex Web Service Token**)

**Step 3:** Click **Generate Token** (or **Create Token**)

**Step 4:** IB displays a long string of letters and numbers — this is your token. Copy it. **Save it somewhere safe — you will not be able to see it again after you leave this page.** If you lose it, you can generate a new one, but you will need to update the app.

> **Security note:** Keep your Flex Token private. It only allows read-only access to your account reports — it cannot place trades or transfer funds.

---

### Part 3 — Enter the Token and Query ID in Trade Log

1. Open Trade Log and go to **🔗 Broker Sync**
2. Scroll down to the **Flex Query** section
3. Enter your **Flex Token** in the "Flex Token" field
4. Enter your **Query ID** in the "Query ID" field
5. Click **💾 Save Flex Settings**

---

### Part 4 — Fetch your data

**In Broker Sync:**
- Click **📥 Fetch via Flex Query** to pull your latest account data (balance, deposits, withdrawals, trade history)
- This can take up to 2 minutes — IB generates the report on their server, so please be patient

**For the equity curve specifically:**
- Go to **📈 Equity Curve** → **🔗 IB Flex Import** tab
- Select your date range
- Click **📥 Fetch Balance History**
- Review the preview table (you will see one row per trading day with ending balance)
- Click **✅ Import** to save all entries to the database
- Switch to the **📈 Chart** tab — the chart may take a moment to populate

---

### Troubleshooting Flex Query

**"Report fetched successfully but contained 0 daily NAV entries"**
Your Flex Query does not have the **Change in NAV** section enabled (or it does not include the **Ending Value** field). Edit the query in IB Account Management and enable that section as described in Step 4 above. Alternatively, enable **Equity Summary by Report Date** or **Net Asset Value** — the app supports all three.

**"IB rejected the request" / Error 1020**
Your token has expired or is incorrect. Go back to IB Account Management → Reports → Flex Queries → Manage Tokens and generate a new token. Update the token in Trade Log → Broker Sync.

**The fetch takes very long or times out**
IB's Flex Web Service sometimes takes 2–3 minutes to generate reports, especially for long date ranges. The app waits up to 2 minutes with automatic retries. If it times out, try uploading the XML directly — see below.

**Uploading the XML directly (reliable fallback)**
If the automatic fetch is not working, you can download the report manually:
1. IB Account Management → Reports → Flex Queries → find your query → click **Run**
2. IB generates the report and offers a download link. Download the `.xml` file.
3. In Trade Log → Broker Sync → click **Or Upload XML Directly** and upload the file.
4. For the equity curve specifically: Equity Curve → IB Flex Import tab → upload the same XML file.

---

## Troubleshooting

### The app does not open
- Make sure the terminal window that you launched the app from is still open
- Try opening `http://localhost:8502` manually in your browser
- Check that port 8502 is not being used by another program

### Live prices are not loading
- Click **⚡ REFRESH LIVE PRICES** in the sidebar — prices do not auto-load
- Check your internet connection
- Yahoo Finance has rate limits — if you refresh too frequently, prices may temporarily fail. Wait 60 seconds and try again.
- If you are connected to IB and have "Use IB live prices" enabled, make sure TWS/Gateway is running

### Earnings dates are wrong or missing
- Earnings dates are sourced from Yahoo Finance and may not always be accurate
- You can override the date on any trade using the **Edit Trade** panel → Earnings Date field
- If Yahoo Finance shows no upcoming date, it may not have a confirmed date yet

### Test email failed — "Connection refused" or "Authentication failed"
- Double-check the SMTP Host, Port, Username, and Password fields
- For Gmail: make sure you used the **App Password**, not your regular Gmail password. Your regular password will not work.
- For Gmail: make sure 2-Step Verification is turned on in your Google account (App Passwords require it)
- Try port `465` with SSL if `587` with TLS is not working (contact your email provider for the correct settings)
- Make sure your email provider has not blocked SMTP access — some require you to explicitly enable "Allow less secure apps" or "SMTP access" in account settings

### Database is corrupt or something looks wrong
- Daily backups are saved automatically in the `backups/` folder
- To restore: close the app, delete or rename `tradelog.db`, copy a backup file from `backups/` and rename it to `tradelog.db`, then restart the app

### The app is slow
- Large numbers of trades (1000+) can slow down the Statistics and Trading Log pages
- Use the date range filter and instrument filters to narrow the data
- Close other browser tabs and background applications

---

## Data & Privacy

All data is stored locally in `tradelog.db` (a SQLite database file) in the same folder as the app. Nothing is sent to any external server except:
- Yahoo Finance API calls for live prices, earnings dates, and FX rates (read-only, no personal data sent)
- Interactive Brokers Flex Web Service calls using your token (read-only, fetches your own account data)
- SMTP email server calls when sending alerts (only to the email address you configured)

Daily backups of the database are saved automatically to the `backups/` folder. Backups are kept as long as the file is under 10 MB.

---

## License

This software is provided as-is for personal use.
