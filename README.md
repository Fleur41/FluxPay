# FluxPay

A secure, offline-first wallet and payroll platform: an **Android app (Kotlin, Jetpack Compose)** backed by a **Django REST API on PostgreSQL**, with a staff back-office.

- **FluxPay staff** onboard businesses and oversee every business, wallet and log from the admin dashboard.
- **Employers** run their business in the app: one cashbook, payroll, suppliers, bills and invoices, reports and their team.
- **Workers** get paid into their own FluxPay wallet, send money, and move it to M-Pesa.

See [How FluxPay works](#how-fluxpay-works) for every workflow from start to end, with examples.

```
FluxPay/
├── android/   Multi-module Android app (MVVM + Clean Architecture, Hilt, Room, Retrofit)
├── backend/   Django + DRF + SimpleJWT API, PostgreSQL
└── .github/   CI for both (unit tests, APK builds, backend tests on Postgres)
```

## Features

| | |
|---|---|
| **Auth** | Register, login (JWT), automatic token refresh, logout with refresh-token blacklisting, password reset by email deep link |
| **Dashboard** | Total balance in your preferred currency, wallets, recent activity, pull to refresh, hide-balances toggle |
| **Transfer** | Validate → confirm recipient name with the server → review → **BiometricPrompt** → send. Idempotency keys make retries safe |
| **Transactions** | Full history grouped by day, search and money-in/out filters (run in SQL, so they work offline), detail screen with share receipt |
| **Statements** | PDF or CSV account statements for a date range, shared from the app |
| **Budget** | Needs / wants / savings planner checked against the staff-set guideline, stored on the device (Room) |
| **Alerts** | SMS and email transaction alerts, switched on or off per channel in Settings |
| **Business accounts** | Owner dashboard, one cashbook per business, team roles (owner, admin, finance, viewer), workers invited by email, phone or join code, payroll with approval and reversal, suppliers with verified payout details, bills (payables) and invoices (receivables), profit and loss and balance sheet, audit log |
| **M-Pesa** | Deposits into wallets and business cashbooks (STK Push), withdrawals to the user's own number, business payouts to phones, paybills and tills. A fake provider stands in during development |
| **Notifications** | Email (any SMTP server, e.g. Gmail) and SMS (Africa's Talking) for payments, payslips, invitations and password resets. Email links open web pages on the server, so they work in any mail app |
| **Receive** | Share your name and account number from the dashboard so people can pay you |
| **Settings** | Profile, preferred currency, theme (system / light / dark), hide balances — all in DataStore |
| **Admin dashboard** | Staff back-office at `/admin/`: onboard businesses, a god's-eye view of every business, live activity, per-business logs, FluxPay's bank cashbook, wallet top-ups, reports and platform rules ([guide](#admin-dashboard)) |
| **Two-step verification** | Authenticator-app codes for staff (always) and business owners and admins (before they can pay or approve) |
| **Security** | Encrypted tokens (Android Keystore AES-GCM), 5-minute inactivity timeout, FLAG_SECURE, no backups, HTTPS-only outside dev, R8 |

## How FluxPay works

### Who uses what

| Who | Where | Does |
|---|---|---|
| **FluxPay staff** | Admin dashboard, `/admin/` | Onboard businesses, put money into wallets from FluxPay's bank, watch every business and log, set platform rules |
| **Owner** | App → **Business** tab | Everything for their business: approves payroll and payments, sets the approval limit, takes money out |
| **Admin** | App → **Business** tab | Approves payroll and payments, manages finance and viewers |
| **Finance** | App → **Business** tab | Prepares payroll and payments, manages workers and suppliers, keeps the books; can't approve |
| **Viewer** | App → **Business** tab | Sees the wallet, payments and books; changes nothing |
| **Worker** | App → **Home** | Gets paid into their own wallet, sees payslips, sends money, sends to M-Pesa |

Everyone uses the same app. The **Business** tab only appears for members of a business, so a worker only sees their own wallet and activity. A person can be both, e.g. the owner of one business and a worker at another.

```
          FluxPay staff (admin)                 Employer (app)                        Worker (app)
  ┌───────────────────────────────┐   ┌────────────────────────────────┐   ┌──────────────────────────────┐
  │ 1 Onboard the business        │──►│ 3 Two-step, team, approval limit│   │                              │
  │ 2 Bank deposit → credit the   │──►│   Business wallet = cashbook    │   │                              │
  │   business wallet             │   │ 4 Invite workers ──────────────────►│ 5 Accept the invitation      │
  │                               │   │ 6 Pay run → approve ───────────────►│ 7 Salary in wallet, payslip  │
  │ 10 Oversee: dashboard, logs,  │   │ 8 Pay suppliers, bills/invoices │   │   Send money / to M-Pesa     │
  │    books, reconciliation      │   │ 9 Books: cashbook, P&L, balance │   │                              │
  └───────────────────────────────┘   └────────────────────────────────┘   └──────────────────────────────┘
```

The examples below use the development data from `python manage.py seed_dev` (every password `Admin@123`): staff `admin@fluxpay.dev`, the business **Kamau Traders** with `owner@kamautraders.test` and `finance@kamautraders.test`, and its workers `worker001@kamautraders.test`… Wallet, receipt and invoice numbers (`7079229416`, `RCT-000042`, `INV-0001`) are from one development database; yours will differ. Times are East Africa Time (Nairobi).

### 1. Staff onboard a business

1. Admin → **Onboard a business** (button on the home page, or Businesses → Onboard a business).
2. Enter the business name, registration number (optional), and the owner's name, email and phone.
3. FluxPay creates the business with its own wallet and books, and makes that person the owner:
   - **New to FluxPay:** an account is created for them with no password, and they're emailed a link to choose one.
   - **Already a FluxPay user:** the business is added to their account. If they never set a password, the link is sent again.

> **Example.** Business *Baraka Bakery*, owner *Baraka Otieno*, `baraka@example.com`, `0712 345 678`. Baraka gets "Baraka Bakery is ready on FluxPay" with a link to `http://localhost:8000/reset-password?...`, chooses a password in the browser, then signs in to the app and finds the business under **Business**.

Anyone can also start a business themselves in the app: **Settings → Start a business**. Recorded as `org.onboarded` (staff) or `org.created` (self-service) in the audit log.

### 2. Money goes into the business wallet

The business wallet **is** the business's cashbook: every shilling in or out is written to it with a category, and its balance always equals the wallet.

| How | Steps | Filed in the books as |
|---|---|---|
| **Bank deposit** (staff) | The money arrives in FluxPay's bank → Admin → **Accounting → Cashbook entries → Add**: *Customer deposit* → open it → **Credit a wallet** → choose the business wallet. See [workflow 10](#10-staff-fluxpays-own-cashbook) | Owner's capital |
| **M-Pesa** (owner/finance) | `POST organizations/{id}/deposits/mpesa/`: an STK Push to their phone | Owner's capital |
| **A customer pays** | The customer uses **Send money** to the business's account number (on the business page) | Sales and revenue |
| **An owner pays in** | The owner sends money from their personal wallet to the business | Owner's capital |

The business can re-file any entry later (Books → tap the entry), e.g. a receipt that was capital, not a sale.

> **Example.** Kamau Traders' wallet is `7079229416`. worker001 sends it KES 500 for an invoice; it appears in the cashbook as money in from worker001, filed under *Sales and revenue*.

### 3. The owner sets up the business

1. **Two-step verification:** Settings → **Two-step verification** → scan the QR code with an authenticator app → enter the code → keep the recovery codes. Owners and admins can look around without it, but can't pay, approve or change anything until it's on.
2. **Team:** Business page → **Team → Invite**: an email and a role (admin, finance or viewer). They get an email; they open the link and accept, signed in with that email. Tap a member to change their role or remove them.
3. **Approval limit:** Business page → **Change**. Pay runs and payments above it need a second person (an owner or admin who didn't prepare it). KES 0 means everything needs approval.

### 4. The employer invites workers

Business page → **Workers → Invite worker**: full name, then **an email**, a phone number or the worker's FluxPay account number, plus monthly salary and job title.

- They get an invitation email (and SMS, if a phone was given) with a 10-character code and a link to a page showing the code with **Open in the FluxPay app**.
- They appear under **Workers → Invited** until they accept. **Resend** gives a new code; the old one stops working.
- **Join code instead:** Workers → **QR icon** → turn the join code on. Workers type the code or scan the QR in the app, and appear under **Requests** for an owner or admin to approve with their salary.
- **Many at once:** Workers → **upload icon** → a CSV with `account_number` (or `phone_number`), `salary`, `job_title`, `employee_number`.

> **Example.** finance@kamautraders.test invites *Achieng Otieno*, `achieng@gmail.com`, KES 30,000, *Cashier*. Achieng receives "Kamau Traders invited you to get paid through FluxPay" with the code `AB12C-3DE45`.

### 5. The worker accepts

1. Install FluxPay and sign in, or **Create an account** (any email and phone; their own password).
2. On Home tap **Do you work for a business?**, or Settings → **My employers → Join a business**.
3. Enter the code (or scan the business's QR) → check the business name → **Accept**.

They move to **Workers → Active** on the employer's side, and their pay goes to their own wallet from now on. The business never sees their password.

### 6. Payroll: prepare, approve, pay

1. **Prepare** (owner, admin or finance): Business page → **Pay workers → New pay run** → keep the title, e.g. *October 2026 salaries*. Every active worker is added at their usual salary.
2. **Check:** tap a worker to change this month's amount (overtime, a deduction) or **Leave out** that worker. The note above the button says what will happen: paid at once, waits for approval, or the wallet is short.
3. **Send pay run.**
   - **Within the approval limit:** everyone is paid at once.
   - **Above it:** status *Waiting for approval*; nobody is paid yet. The approvers see "1 to approve" on their dashboard.
4. **Approve** (an owner or admin who didn't prepare it): open the run → **Approve and pay everyone**. Or **Reject** with a reason; nobody is paid.
5. **Take back a wrong payment** (owners and admins, within 7 days, a platform rule): open the paid run → tap the worker → **Take back** with a reason. The money returns to the business wallet if the worker still has it, and they're told by email and SMS.

> **Example.** finance prepares *October 2026 salaries* for all of Kamau Traders' active workers. The approval limit is KES 0, so it waits. owner@kamautraders.test signs in (password plus authenticator code), opens **Needs your attention → 1 pay run to approve**, approves, and all 200 wallets are credited in one transaction. Each worker gets "You received KES … from Kamau Traders".

### 7. The worker uses their pay

| Want to | Where |
|---|---|
| See the salary | **Home**: the balance and the **My pay** section (each payslip, *Paid* or *Taken back*); Settings → **My employers** for the businesses that pay them |
| Pay someone on FluxPay | **Send** tab: their 10-digit account number → amount → review → fingerprint, face or screen PIN |
| Move it to M-Pesa | Home → **M-Pesa** → amount → confirm. Only to the M-Pesa number on their profile. The money leaves the wallet at once and comes back if M-Pesa fails it |
| Statement | **Activity** tab → download icon → PDF or CSV for a date range |

> **Example.** worker001 (`worker001@kamautraders.test`) sends KES 200 to M-Pesa 0701 000 001. History shows a pending withdrawal; it completes when M-Pesa confirms (in development, the fake provider confirms it at the next status check, within about 5 minutes).

### 8. Paying suppliers, bills and invoices

**Pay a supplier.** Business page → **Pay suppliers**:

1. **Add supplier**: name, what they are (supplier, contractor, landlord, utility...), and how to pay them: M-Pesa number, paybill (+ account), till, bank account or FluxPay account.
2. An **owner or admin checks the payout details**, e.g. against the supplier's invoice: tap the supplier → **I've checked these details**. It must be someone other than the person who entered them (unless there's no one else), so nobody can quietly redirect payments to their own number.
3. Tap the supplier → **Pay** → amount and note. Within the approval limit it goes out at once; above it, it waits under **Payments** for an owner or admin to approve.

**Bills (payables) and invoices (receivables).** Business page → **Books → Bills & invoices**:

| | Bill: money the business owes | Invoice: money owed to the business |
|---|---|---|
| Record | **+ Bill to pay**: supplier, amount, expense category, due date | **+ Invoice to collect**: customer, amount, income category, due date |
| In the books at once | Expense, and *Accounts payable* goes up | Income, and *Accounts receivable* goes up |
| Paid when | You pay the supplier, then open the bill → **Link the payment from the cashbook** | The customer pays in, then open the invoice → **Link the money received** |
| Then | *Accounts payable* goes down; the expense is counted once, not twice | *Accounts receivable* goes down; part payments show *Part paid* |

Totals show as **We owe** and **Owed to us**, with overdue amounts, on the dashboard and in Books. A bill or invoice entered by mistake can be cancelled until something is linked to it.

> **Example.** Kamau Traders records invoice **INV-0001**: customer *worker001*, KES 500, *Sales and revenue*. worker001 sends KES 500 to the business wallet `7079229416`. finance opens INV-0001 → **Link the money received** → picks the 500 → **Paid**. The P&L shows KES 500 of sales once, and the balance sheet still balances.

### 9. The books and the owner's dashboard

**Dashboard** (Business tab → the business): wallet balance, money in and out and profit this month, **Needs your attention** (pay runs and supplier payments to approve, join requests, supplier details to check, overdue bills and invoices), workers and monthly payroll, what's owed each way, quick links, and the latest cashbook lines.

**Books** has three tabs:

- **Cashbook**: every movement on the wallet with a running balance, for this month, last month or this year. Tap an entry to file it under another category.
- **Bills & invoices**: see [workflow 8](#8-paying-suppliers-bills-and-invoices).
- **Reports**: profit and loss (income less expenses) and the balance sheet: what the business has (wallet, receivables), what it owes (payables), and owners' equity. It shows **Balances** when assets = liabilities + equity.

Categories: Owner's capital, Owner's drawings, Sales and revenue, Interest earned, Other income, Salaries and wages, Allowances, Bonuses, Commissions, Purchases and suppliers, Contractors, Other business expenses, plus the business's own.

### 10. Staff: FluxPay's own cashbook

Admin → **Accounting → Cashbook entries** is FluxPay's bank book: one line for every shilling that moves in or out of FluxPay's real bank accounts (**Accounting → Bank accounts**, e.g. *Equity Bank – Customer funds (safeguarding)*). Money can't appear in a wallet unless it first arrived in the bank and was recorded here.

```
Money lands in the bank  →  Record it (Customer deposit)  →  Credit a wallet  →  Reconcile with the bank statement
                            RCT-000042, "Unallocated"        "Fully allocated"    "Cleared"
```

| Category | Use it for | Effect |
|---|---|---|
| Customer deposit | Money paid in for a customer or business | Waits as unallocated until credited to wallets |
| Customer withdrawal | Paid a customer out of their wallet (cash or bank) | Debits the wallet number you enter |
| Bank payout requested in the app | Created when staff confirm a bank payout from **Payments → Bank payouts to send** | Settles a payout the customer requested |
| Owner's capital / drawings | FluxPay's owners putting money in or taking it out | FluxPay equity |
| Interest from the bank / Other income | Money paid to FluxPay itself | FluxPay income |
| Bank charges / Business expense | FluxPay's own costs | FluxPay expenses |
| Transfer between FluxPay bank accounts | Moving money between FluxPay's banks | Two linked entries |

Entries are never edited or deleted: **Reverse this entry** posts an opposite one, with a reason. Monthly, **Accounting → Reconcile a bank account** ticks entries off against the bank statement.

> **Example: a KES 1,000 cash deposit for worker001, start to end.**
> 1. **Add**: Customer deposit, *Equity Bank – Customer funds*, today, KES 1,000, from *Peter Kariuki*, slip `DEMO-SLIP-001` → **RCT-000042**, *Unallocated 1,000.00*.
> 2. On RCT-000042 → **Credit a wallet** → worker001's wallet `3615888022`, KES 1,000, reason → wallet 103,700 → **104,700**; the deposit is fully allocated.
> 3. (Only to undo the demo) Money → **Top-ups & corrections → Add**: *Correction*, from RCT-000042, KES 1,000 → wallet back to 103,700, the 1,000 unallocated again.
> 4. RCT-000042 → **Reverse this entry**, reason *"Demo entry for staff training"* → **PAY-000011** cancels it. Both stay in the books and the audit log, and **Customer money** on the home page still says *Fully backed*.

### 11. Staff: oversight

- **Home page**: totals for all businesses (businesses, money in business wallets, payroll this month, workers), **every business** with its owner, wallet, workers, payroll, money in and out, what it owes and is owed, last activity and **Books / Logs** links, plus a **Live activity** feed and **Needs attention**.
- **Audit log**: every sign-in, payment, approval and staff action, hash-chained so edits or deletions are detected. Filter by **business** to see one business's whole history.
- **Businesses → Business books**: any business's cashbook, P&L, balance sheet and a reconciliation check (wallet = ledger = cashbook).
- **Businesses → Bills and invoices**, **Pay runs**, **Business payments**, **Workers**: every business's records, read-only.
- **Access → Staff accounts / Staff groups & permissions**: who can do what (see [Give staff access](#give-staff-access)). Suspend a business from its page.

### Notifications

| Event | Email | SMS |
|---|---|---|
| Money sent or received (transfers, salaries, supplier payments) | ✓ | ✓ |
| Payslip paid or taken back | ✓ | ✓ |
| Worker invitation (code + link) | ✓ | ✓ if a phone was given |
| Team invitation | ✓ | |
| Business onboarded (with a set-password link for new owners) | ✓ | |
| Password reset | ✓ | |

Each user can switch SMS or email alerts off in **Settings**. Every alert is listed under Admin → **Email & SMS alerts**, with failures. Links in emails open pages on the server (`FLUXPAY_WEB_URL`):

| Page | For |
|---|---|
| `/reset-password?uid=…&token=…` | Choose a new password in the browser; works once |
| `/join?code=…` | A worker's invitation code, with **Open in the FluxPay app** |
| `/join-business?token=…` | A team invitation, with **Open in the FluxPay app** |

## Android architecture

```
:app ──────────────► :feature:auth  :feature:dashboard  :feature:transfer  :feature:transactions  :feature:budget
 │                    :feature:business  :feature:settings
 │                        │  (presentation + feature use cases; depend only on :core:domain / :core:ui)
 │                        ▼
 ├────────────────► :core:ui ──► :core:domain ──► :core:common
 └────────────────► :core:data ──► :core:network (Retrofit, OkHttp, Moshi)
                              └──► :core:database (Room)
```

- **Clean Architecture.** Features see only repository *interfaces* in `:core:domain`. `:app` wires the implementations from `:core:data` in through Hilt, so a feature can't reach Retrofit or Room directly.
- **Offline-first.** Screens observe Room `Flow`s; refreshes fetch from Django and write to Room, which re-emits. If the network fails you still see your last balances with an “offline” banner. Transfers are never queued offline.
- **Feature packages** follow `domain/{model,usecase}`, `presentation/{components,state,viewmodel}`, `navigation/`. Shared data access lives once in `:core:data` rather than being duplicated per feature.
- **NetworkResult.** Every API call returns `NetworkResult.Success | Error | Loading`. Errors carry the Django error `code` (e.g. `insufficient_funds`) and a human message.

### Where each requirement lives

| Requirement | Implementation |
|---|---|
| MVVM + Coroutines/Flow | `StateFlow` UI state in every `*ViewModel`, `viewModelScope`, `stateIn(WhileSubscribed)` |
| Dispatchers | `@Dispatcher(IO/Default/Main)` qualifiers in `core/common/dispatcher`; repositories use `withContext(io)` / `flowOn(io)` |
| **Handler & Looper** | `app/.../session/SessionTimeoutViewModel.kt` — `HandlerThread` ticker + main-`Looper` handler; cleaned up in `onCleared()` |
| **Builder** | `TransferRequest.Builder` (validates on `build()`), plus OkHttp/Retrofit/Room builders |
| **Factory** | `TransactionDetailViewModel.Factory` (`@AssistedFactory`) — ViewModel created with a runtime id from a tap or deep link |
| **Adapter** | `core/data/mapper/DtoAdapters.kt` (DTO → Entity → Domain) and `core/ui/adapter/TransactionListAdapter.kt` (domain → typed LazyColumn items with keys/content types) |
| JWT interceptor | `AuthInterceptor` adds `Bearer`; `TokenAuthenticator` refreshes on 401 using a separate client (no recursion) |
| Token storage | `SecureTokenStore` — AES-256-GCM key in Android Keystore, ciphertext in DataStore |
| DataStore prefs | `PreferencesRepositoryImpl` — currency, theme, hide balances |
| Biometrics | `feature/transfer/.../BiometricAuthenticator.kt` (STRONG + device credential on API 30+) |
| Launch mode & deep links | `MainActivity` is `singleTop`; links go through `onNewIntent` → `MainViewModel` → `NavController`. Links opened while signed out wait for login |
| Memory leaks | No `Context` in ViewModels (only `@ApplicationContext` in DI modules); jobs tied to `viewModelScope`; LeakCanary in `debugImplementation` |
| Build variants | `dev` / `staging` / `prod` flavors × `debug` / `release` (devRelease disabled) |
| Play Store release | R8 + resource shrinking, `proguard-rules.pro`, signing from `keystore.properties` |

### Deep links

| Link | Opens |
|---|---|
| `fluxpay://transaction/{id}` or `https://fluxpay.app/transaction/{id}` | Transaction detail (after login if needed) |
| `fluxpay://reset-password?uid=…&token=…` | Choose a new password |
| `fluxpay://join-employer?code=…` | Accept a worker invitation |
| `fluxpay://join-employer?business=…` | Ask to join with a business's join code (its QR code) |
| `fluxpay://join-business?token=…` | Accept an invitation to a business's team |

Emails don't use these directly, because mail apps won't open app-only links: they link to web pages on the server (`/reset-password`, `/join`, `/join-business`) that work in any browser and have an **Open in the FluxPay app** button. See [Notifications](#notifications).

Try one on an emulator:

```bash
adb shell am start -a android.intent.action.VIEW -d "fluxpay://transaction/<transaction-uuid>" com.fluxpay.app.dev
```

## Quick start

### 1. Backend (Django + PostgreSQL)

```bash
cd backend
cp .env.example .env
docker compose up --build          # API on http://localhost:8000, Postgres on :5432, plus Redis and the worker
docker compose exec api python manage.py createsuperuser   # for Django admin at /admin/
docker compose exec api python manage.py seed_dev --reset    # optional: demo data (wipes the database first)
```

`seed_dev` creates staff `admin@fluxpay.dev`, five businesses (e.g. **Kamau Traders**, owner `owner@kamautraders.test`, finance `finance@kamautraders.test`) each with 20 active workers (`worker001@…` to `worker020@…`) and funded from a bank receipt, all with the password `Admin@123`. It refuses to run unless `DEBUG` is on. After changing code, rebuild the containers with `docker compose up -d --build api worker`; after changing `.env`, `docker compose up -d --force-recreate api worker`.

#### Email, SMS and M-Pesa in development

| | Until set up | To switch on (in `backend/.env`) |
|---|---|---|
| **Email** | Printed in the server log (`docker compose logs api`) | `EMAIL_HOST=smtp.gmail.com`, `EMAIL_PORT=587`, `EMAIL_HOST_USER=you@gmail.com`, `EMAIL_HOST_PASSWORD=<16-letter app password>` (Google Account → Security → 2-Step Verification → App passwords). Mail then comes from that address |
| **SMS** | Printed in the server log | `AFRICASTALKING_USERNAME` and `AFRICASTALKING_API_KEY`. A key made in the Sandbox only works with the username `sandbox` and only reaches their online simulator; real phones need a live app's username and SMS credit |
| **M-Pesa** | A fake provider: deposits and withdrawals are accepted and complete at the next status check (about 5 minutes) | `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_PASSKEY`, `FLUXPAY_PUBLIC_URL` (and the initiator settings for payouts) for Safaricom Daraja |
| **Links in emails** | `http://localhost:8000/…` (works on the computer, and on a phone connected with `adb reverse`) | `FLUXPAY_WEB_URL=https://<public host>` |

Addresses at reserved test domains (`*.test`, `example.com`, …), like the seed data's, are only logged, never sent. Check the set-up with:

```bash
docker compose exec api python manage.py test_notifications --email you@gmail.com --phone 0712345678
```

Or without Docker (uses SQLite unless `DATABASE_URL` is set):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
python manage.py test
```

The server runs on **East Africa Time** (`TIME_ZONE=Africa/Nairobi`, and `TZ` for the containers' clocks): the admin, logs, business dates, statements and alerts all show Nairobi time. The database stores exact moments, so the zone can be changed without touching data.

Business rules are data, not code: staff set the currencies (with each one's per-transaction minimum and maximum and an optional signup bonus), the default currency, statement range, invitation expiry, the app's inactivity timeout and the budget guideline in the [admin dashboard](#admin-dashboard) under **Settings → Platform rules**. Every change is audited, and the app reads them from `GET /api/v1/config/`. New wallets start at 0; a signup bonus, when staff set one, is paid from a system Promotions account so the ledger always balances.

### 2. Android

Open `android/` in Android Studio (Ladybug or newer, JDK 17), choose the **devDebug** variant and run on an emulator. `dev` talks to `http://10.0.2.2:8000/` — your computer's localhost.

```bash
cd android
./gradlew assembleDevDebug                    # debug APK, logging on, LeakCanary on
./gradlew testDebugUnitTest testDevDebugUnitTest
./gradlew bundleProdRelease                   # Play Store bundle (needs keystore.properties)
./gradlew assembleStagingRelease -Pfluxpay.stagingUrl=https://your-staging-host/
```

| Variant | App ID | API | Notes |
|---|---|---|---|
| devDebug | `com.fluxpay.app.dev` | `http://10.0.2.2:8000/` | Cleartext allowed for local hosts only, HTTP logging |
| stagingDebug / stagingRelease | `com.fluxpay.app.staging` | `https://staging-api.fluxpay.app/` | Release-like, FLAG_SECURE |
| prodRelease | `com.fluxpay.app` | `https://api.fluxpay.app/` | R8 minified, no logging |

Override any host with `-Pfluxpay.devUrl=…`, `-Pfluxpay.stagingUrl=…` or `-Pfluxpay.prodUrl=…`.

## Connecting the Android app to the backend

The app finds the API through one value, `BuildConfig.BASE_URL`, which the build flavor sets. Nothing else in the code holds a host name.

```
android/app/build.gradle.kts        BASE_URL per flavor (or -Pfluxpay.<flavor>Url=…)
        │
app/di/AppModule.kt                 AppConfig(baseUrl = BuildConfig.BASE_URL)
        │
core/network/di/NetworkModule.kt    Retrofit.baseUrl(config.baseUrl) + OkHttp (15 s connect, 30 s read)
        │   AuthInterceptor          adds "Authorization: Bearer <access>"
        │   TokenAuthenticator       on 401, calls auth/refresh/ once and retries
        ▼
core/network/api/FluxPayApi.kt      @GET("api/v1/accounts/") … → Django REST API
```

The repositories in `:core:data` call `FluxPayApi`, save the results to Room, and the screens show what's in Room. So once the base URL points at a running backend, every screen is connected.

### Check the backend is reachable first

```bash
curl http://localhost:8000/health/          # {"status": "ok"}
curl http://localhost:8000/api/v1/config/   # public: currencies, limits, timeouts the app needs at start-up
```

### Emulator (default)

Start the backend on all interfaces (`docker compose up`, or `python manage.py runserver 0.0.0.0:8000`) and run **devDebug**. The emulator reaches your computer at `10.0.2.2`, which is the dev default, so no changes are needed.

### Physical phone over USB

Forward the phone's port 8000 to your computer, then build with the loopback address:

```bash
adb reverse tcp:8000 tcp:8000
cd android && ./gradlew installDevDebug -Pfluxpay.devUrl=http://127.0.0.1:8000/
```

Use `adb reverse` rather than your computer's Wi-Fi IP: the dev network security config (`app/src/dev/res/xml/network_security_config.xml`) allows plain HTTP only to `10.0.2.2`, `localhost` and `127.0.0.1`, so a LAN address like `http://192.168.1.20:8000/` is blocked.

### Phone over Wi‑Fi (wireless debugging)

On the phone: Developer options → **Wireless debugging** → on, then **Pair device with QR code** (Android Studio's *Pair devices using Wi‑Fi* shows the QR code), or pair with a code:

```bash
adb pair <phone-ip>:<pairing-port> <pairing-code>     # once; the phone remembers the computer
adb connect <phone-ip>:<port>                          # the port shown under Wireless debugging
adb reverse tcp:8000 tcp:8000                          # needed again after every reconnect
cd android && ./gradlew installDevDebug -Pfluxpay.devUrl=http://localhost:8000/
```

The connection drops when the phone sleeps for long, changes Wi‑Fi or gets a new IP address; connect and `adb reverse` again. One APK built with `http://localhost:8000/` works on both the emulator and phones, as long as each has `adb reverse`.

### Phone without a cable, or sharing with testers

Put the local API behind an HTTPS tunnel and point the app at it:

```bash
cloudflared tunnel --url http://localhost:8000           # prints https://<random>.trycloudflare.com
# backend/.env:  DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,10.0.2.2,<random>.trycloudflare.com
./gradlew installDevDebug -Pfluxpay.devUrl=https://<random>.trycloudflare.com/
```

### Staging and production

`staging` and `prod` builds talk HTTPS only, to `https://staging-api.fluxpay.app/` and `https://api.fluxpay.app/`. Point them elsewhere with `-Pfluxpay.stagingUrl=…` or `-Pfluxpay.prodUrl=…`. On the server, run the `ghcr.io/fleur41/fluxpay-api` image behind a TLS proxy that sets `X-Forwarded-Proto` (Django trusts it when `DJANGO_DEBUG=false`), and set:

| Variable | Value |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | long random string |
| `DJANGO_ALLOWED_HOSTS` | the API's host name, e.g. `api.fluxpay.app` |
| `DATABASE_URL` | the PostgreSQL connection string |
| `CELERY_BROKER_URL` | Redis, for background jobs (also run a worker and one `celery beat`) |

`CORS_ALLOWED_ORIGINS` is only for browser clients; the Android app doesn't need it.

### When it doesn't connect

| Symptom | Cause | Fix |
|---|---|---|
| `CLEARTEXT communication … not permitted` | HTTP to a host the dev config doesn't allow, or HTTP in a staging/prod build | Use `adb reverse` with `127.0.0.1`, or an HTTPS URL |
| `400 Bad Request` from Django | The host isn't in `DJANGO_ALLOWED_HOSTS` | Add it to `backend/.env` and restart |
| `failed to connect to /10.0.2.2` | Backend not running, or bound to `127.0.0.1` only | Run `runserver 0.0.0.0:8000`, or use Docker |

Turn on HTTP logging (on in `dev` and `staging`) and filter Logcat by `okhttp.OkHttpClient` to see each request and response; the `Authorization` header is redacted.

### Release signing

```bash
keytool -genkeypair -v -keystore android/fluxpay-release.jks -alias fluxpay -keyalg RSA -keysize 4096 -validity 10000
cp android/keystore.properties.example android/keystore.properties   # then fill in the passwords
```

Both files are git-ignored. Without them, release builds are signed with the debug key (fine for CI, not for Play).

## Admin dashboard

FluxPay's back-office is Django admin, styled with [Unfold](https://unfoldadmin.com/) in the app's purple. Staff use it to watch the platform, help customers and change business rules without a code release.

### Open it

```bash
cd backend
docker compose exec api python manage.py createsuperuser    # or: python manage.py createsuperuser
```

Then go to **http://localhost:8000/admin/** and sign in with that email and password. In production it is `https://<api-host>/admin/`. Customer accounts can't sign in here; only users marked **Staff** can.

A label next to the FluxPay name shows **Development** (yellow) or **Production** (red), so you always know which system you are changing. Press **Cmd/Ctrl + K** to jump to any screen or record.

### The home page

| Panel | Shows |
|---|---|
| **Onboard a business** (button) | Set up a business and its owner ([workflow 1](#1-staff-onboard-a-business)) |
| **Businesses** | Number of businesses (active, suspended), money in business wallets, payroll paid this month, workers on payroll |
| **Every business** | One row per business, most recently active first: owner, status, wallet, workers, payroll, money in and out this month, what it owes and is owed, last activity, and **Books** / **Logs** links |
| **Live activity** | The latest things that happened across FluxPay, with the business each concerns |
| **Active customers** | Customer count, and how many joined in the last 7 days |
| **Transfers today** | Number of transfers since midnight, and the volume per currency |
| **Top-ups today** | Staff top-ups and corrections posted today |
| **Failed transactions (7 days)** | Held payouts that were returned |
| **Customer money held** | Total balance and wallet count per currency (FluxPay's own system accounts excluded) |
| **Needs attention** | Customer deposits waiting to be credited to a wallet, business payments waiting for approval, external payments flagged for review, bank payouts waiting to be sent, alerts that failed to send. Each links to the filtered list |
| **Customer money** | FluxPay's bank against what it owes customers: *Fully backed* or *Shortfall* |
| **Audit log** | Tamper check: confirms no audit record has been altered or removed |
| **Recent top-ups & corrections** | The last six, with who posted them |

Staff pass two-step verification (an authenticator app) once per session before any page opens; the first time, they set it up there. Opening a business's records is written to that business's own audit log (`staff.viewed_business_data`), which its owners can read. Staff only see the panels and menu items their permissions allow. The sidebar shows red counts next to **Business payments**, **Payments** and **Email & SMS alerts** when something is waiting.

### What each screen is for

| Sidebar | Screen | Staff can |
|---|---|---|
| Customers | **People** | Search by email, name or phone; filter by staff, active or join date; deactivate a user |
| | **Wallets** | Look up any wallet by number, owner or business, with balance and status |
| Money | **Top-ups & corrections** | Credit a wallet from a bank receipt, or take money back (see below) |
| | **Transactions** | Every ledger line, filterable by type, category, status and date; search by reference |
| | **Transfers** | Every customer-to-customer transfer |
| Accounting | **Cashbook entries** | FluxPay's bank book: record money in and out of FluxPay's banks, credit wallets from deposits, reverse mistakes ([workflow 10](#10-staff-fluxpays-own-cashbook)) |
| | **Financial reports**, **Reconcile a bank account**, **Journals**, **Chart of accounts**, **Bank accounts** | FluxPay's own books: trial balance, P&L, balance sheet, safeguarding; tick entries off against bank statements; rename or close bank accounts |
| Businesses | **Onboard a business** | Create a business and its owner; the owner is emailed |
| | **Businesses** | Suspend or reactivate a business; see its members and approval threshold |
| | **Business payments** | Every payment out of a business cashbook (salaries, allowances, supplier payments...) with its type, status and reference. Approving is done by the business's own approvers in the app, not by staff |
| | **Invitations** | Pending, accepted and expired team invitations |
| | **Pay runs**, **Workers** | Every business's payroll and worker register |
| | **Business books** | Pick a business: its cashbook, P&L, balance sheet and reconciliation |
| | **Business cashbooks**, **Bills and invoices** | Every business's cashbook lines, bills and invoices |
| External payments | **Payments** | Deposits and withdrawals through payment providers; filter **Needs review**. Filter **Bank payouts to send** for the bank payouts staff send from FluxPay's bank: open one for its payout details, send it, then **Confirm or fail** it with the bank's reference (this also records it in the cashbook). A payout M-Pesa never answered is flagged for review and settled the same way, after checking the M-Pesa portal |
| | **Provider callbacks** | Raw callbacks received from providers, and what happened to each |
| Alerts & compliance | **Email & SMS alerts** | Every alert sent, filterable by channel, event and status (use **Failed** to find problems) |
| | **Audit log** | Who did what and when, across the app and the admin; filter by **business** for one business's log |
| Settings | **Platform rules** | Default currency, statement range, invitation expiry, app inactivity timeout, budget guideline |
| | **Currencies & limits** | Enable or disable currencies; set per-transaction minimum and maximum and the signup bonus |
| Access | **Staff accounts**, **Staff groups & permissions** | Who can sign in here and what they may do (see below) |

Wallets, transactions, transfers, payments, alerts and the audit log are **view-only**: money only moves through the app's services, so staff can't edit or delete ledger records. Businesses are created by **Onboard a business** (or by customers in the app) and are never deleted, only suspended.

### Top up or correct a wallet

A top-up always comes from money that really arrived in FluxPay's bank, so the bank always backs what customers hold.

1. Record the money under **Accounting → Cashbook entries → Add** as a *Customer deposit* (receipt `RCT-…`).
2. Open the receipt → **Credit a wallet** (or **Money → Top-ups & corrections → Add** and choose the receipt).
3. Pick the wallet, **Top-up**, the amount (up to what's left on the receipt) and a reason of at least 10 characters, e.g. *"Cash deposited at Equity Ruiru, slip 1042"*.
4. Save. The wallet changes immediately and the customer gets an email/SMS alert.

A **Correction** takes money back from a wallet to the receipt it came from. The full example is in [workflow 10](#10-staff-fluxpays-own-cashbook).

Rules:
- The currency's per-transaction limits apply, which guards against an extra zero (KES 500,000 by default; credit a big receipt in several parts).
- A correction can't take a wallet below zero.
- Adjustments can't be edited or deleted. To undo one, post the opposite adjustment.
- Every adjustment is double-entry against a **Manual adjustments** system account, so the ledger always balances, and it appears in the customer's history as *Adjustment by FluxPay*.

### Change business rules

- **Settings → Platform rules:** There is one settings record; the link opens it directly. The budget guideline's three percentages must add up to 100.
- **Settings → Currencies & limits:** Edit a currency's limits or signup bonus, or untick **Enabled** to stop new use. Currencies can't be deleted, because wallets refer to them. Keep the signup bonus at 0 unless you're running a promotion.

Changes apply straight away: the app reads them from `GET /api/v1/config/` the next time it loads. Each change is written to the audit log with the old and new values.

### Give staff access

Don't give everyone superuser. Instead:

1. **Access → Staff groups & permissions → Add**, e.g. *Support* (view permissions on people, wallets, transactions, alerts) or *Finance* (add **Can top up or correct customer wallets**, plus view on adjustments and wallets).
2. **Customers → People**, open the person, tick **Staff status**, and add them to the group. Leave **Superuser status** off. **Access → Staff accounts** lists everyone who can sign in here.

Only users with the **Can top up or correct customer wallets** permission can post adjustments. Recording bank money needs **Can record bank receipts and payments**; onboarding businesses needs **Can add organization**; the business overview needs **Can view organization**.

### Production notes

- The admin's styles are served by the API itself (WhiteNoise); the Docker image runs `collectstatic` on start, so there is nothing else to host.
- Create the first superuser on the server with `docker run … ghcr.io/fleur41/fluxpay-api python manage.py createsuperuser`, or the equivalent for your host.
- `/admin/` is public on the internet. Use strong passwords, and consider limiting it by IP at your proxy.

## API

All endpoints are under `/api/v1/` and use `Authorization: Bearer <access>` unless marked public. Errors always look like `{"error": {"code": "...", "message": "...", "details": {...}}}`.

| Method | Path | |
|---|---|---|
| POST | `auth/register/` | public — creates user + wallet, returns tokens |
| POST | `auth/login/` | public — `{email, password}` → `{access, refresh, user}`, or with two-step verification on `{mfa_required: true, mfa_token}` |
| POST | `auth/login/mfa/` | public — `{mfa_token, code}` → `{access, refresh, user}`; the code is from the authenticator app, or a recovery code. 10/min; 5 wrong codes lock it for 15 minutes |
| GET, POST | `auth/mfa/` , `auth/mfa/setup/` , `auth/mfa/enable/` , `auth/mfa/disable/` , `auth/mfa/recovery-codes/` | two-step verification: status (`enabled`, `required`); a new secret and `otpauth_uri`; `{code}` turns it on and returns 10 recovery codes once; `{password, code}` turns it off; `{code}` replaces the recovery codes. Business owners and admins without it can view a business but get `mfa_required` (403) for anything else |
| POST | `auth/refresh/` | public — rotates refresh token |
| POST | `auth/logout/` | blacklists the refresh token |
| GET/PATCH | `auth/me/` | profile |
| POST | `auth/password-reset/` , `auth/password-reset/confirm/` | public |
| GET | `accounts/` | your wallets |
| GET | `accounts/lookup/?account_number=` | recipient's masked name + currency |
| GET | `transactions/?type=&category=&account=&search=&date_from=&date_to=&page=` | paginated, newest first |
| GET | `transactions/{id}/` | one transaction |
| POST | `transfers/` | `{source_account_id, destination_account_number, amount, note, idempotency_key}` |
| GET | `config/` | public — platform settings the app reads at start-up |
| GET | `statements/?account_id=&date_from=&date_to=&file_format=pdf\|csv` | statement file, 10/min |
| GET/PATCH | `notifications/settings/` | SMS and email alert preferences |
| GET | `payments/` , `payments/{id}/` | your external deposits and withdrawals (personal wallets only), with `receipt` once confirmed |
| POST | `deposits/mpesa/` | `{account_id, phone_number, amount, idempotency_key}`: STK Push; whole shillings; answers 202, poll `payments/{id}/` |
| POST | `withdrawals/mpesa/` | `{account_id, amount, idempotency_key}`: to the M-Pesa number on your profile only; the money leaves the wallet at once and comes back if M-Pesa fails it |
| GET/POST | `organizations/` | your businesses; create one `{name, registration_number?}` (you become its owner) |
| GET/PATCH | `organizations/{id}/` | one business |
| GET, PATCH/DELETE | `organizations/{id}/members/` , `…/members/{member_id}/` | members and their roles |
| GET/POST, DELETE | `organizations/{id}/invitations/` , `…/invitations/{invitation_id}/` | invite by email; revoke |
| POST | `invitations/accept/` | join a business with an invitation token |
| GET | `organizations/{id}/accounts/` , `…/transactions/` , `…/statements/` , `…/audit-events/` | the business cashbook (its one wallet), history, statements and audit log |
| GET/POST | `organizations/{id}/payments/?status=&type=&worker=&pay_run=` | every payment out of the cashbook (`pay_run=none`: only one-off payments). POST `{type, worker_id \| destination_account_number, amount, note, books_category?, idempotency_key}`; `type` is `SALARY`, `ALLOWANCE`, `BONUS`, `COMMISSION`, `OTHER_WORKER` (need `worker_id`), or `SUPPLIER`, `VENDOR`, `CONTRACTOR`, `EXPENSE`, `OTHER` (need an account number) |
| POST | `organizations/{id}/payments/{payment_id}/{approve\|reject\|cancel}/` | decide on a payment waiting for approval (`{note}`) |
| POST | `organizations/{id}/payments/{payment_id}/reverse/` | take back a paid payment, `{reason}`; owners and admins, within the reversal window |
| GET/POST | `organizations/{id}/beneficiaries/?search=&kind=&active=all` | saved suppliers, contractors, landlords... POST `{name, kind, method, …details}`; `method` is `FLUXPAY` (`account_number`), `MPESA_MOBILE` (`mpesa_phone`), `MPESA_PAYBILL` (`paybill_number`, `paybill_account`), `MPESA_TILL` (`till_number`) or `BANK` (`bank_name`, `bank_account_name`, `bank_account_number`, optional `bank_branch`, `bank_swift_code`). Viewers see account numbers masked |
| GET/PATCH/DELETE | `organizations/{id}/beneficiaries/{beneficiary_id}/` | one beneficiary; changing payout details unverifies it; DELETE archives |
| POST | `organizations/{id}/beneficiaries/{beneficiary_id}/verify/` | an owner or admin confirms the payout details; not the person who entered them, unless they are the only approver. Only verified beneficiaries can be paid: POST `payments/` with `{beneficiary_id, amount, idempotency_key}` (`type` defaults from the kind). M-Pesa and bank beneficiaries are paid out of the cashbook at once; the payment stays `PROCESSING` until M-Pesa or FluxPay staff confirm it (`payout_method`, `payout_receipt`), or `FAILED` with the money back. A `OWN_ACCOUNT` beneficiary takes `WITHDRAWAL`s (owners only, filed as drawings) |
| POST | `organizations/{id}/deposits/mpesa/` | `{phone_number, amount, idempotency_key}`: STK Push into the business cashbook (filed as owner's capital; re-file it in the books if it was a sale) |
| GET | `organizations/{id}/external-payments/` , `…/external-payments/{payment_id}/` | the cashbook's M-Pesa and bank deposits and payouts |
| GET/POST | `organizations/{id}/workers/?status=&search=&active=all` | the worker register (active workers unless `status` is given: `INVITED`, `PENDING_ACTIVATION`, `SUSPENDED`, `DEACTIVATED`). POST invites someone: `{full_name, email and/or phone_number, salary, job_title?, employee_number?}` or `{account_number, salary, …}`; they get a code by email/SMS and become `ACTIVE` only when they accept. `workers/import/` invites many (JSON rows or CSV) |
| GET/PATCH/DELETE | `organizations/{id}/workers/{worker_id}/` | one worker; PATCH pay details; DELETE removes them (or cancels the invitation/request), keeping their pay history |
| POST | `organizations/{id}/workers/{worker_id}/{approve\|decline\|suspend\|reactivate\|resend-invitation}/` | approve a join request `{salary, job_title?, employee_number?}` (owners, admins); decline or suspend `{reason}`; suspended workers can't be paid |
| GET/POST/DELETE | `organizations/{id}/worker-join-code/` | the business's join code and its QR link (owners, admins). POST makes a new one (the old stops working), DELETE switches it off |
| GET | `organizations/{id}/books/cashbook/?start=&end=` , `…/books/summary/?start=&end=` | the business cashbook with running balance; profit and loss for the period and the balance sheet at its end (assets, liabilities, equity) |
| GET/POST | `organizations/{id}/books/categories/` | the business's categories; POST `{name, type: INCOME\|EXPENSE}` adds its own |
| PATCH | `organizations/{id}/books/entries/{entry_id}/` | re-file a cashbook entry `{category_id, note?}` |
| GET/POST | `organizations/{id}/books/invoices/?kind=BILL\|INVOICE&open=1` | bills (payables) and invoices (receivables), with `totals` owed each way and overdue. POST `{kind, party, amount, category_id, description?, issue_date?, due_date?}`: a bill needs an expense category, an invoice an income one |
| GET | `organizations/{id}/books/invoices/{invoice_id}/` , `…/payable-entries/` | one bill or invoice with its payments; the cashbook entries that could pay it |
| POST | `organizations/{id}/books/invoices/{invoice_id}/pay/` , `…/cancel/` | `{entry_id}` links a cashbook entry that paid it (moves it to payables/receivables); `{reason}` cancels one with nothing paid |
| GET | `organizations/{id}/books/reconciliation/` | does the business's money add up: wallet = ledger = cashbook, every movement has its cashbook line, payment statuses match their money, outside payouts settled. `balanced`, `problems`, `attention` (in flight, possible duplicates) |
| GET/POST | `organizations/{id}/pay-runs/` , `…/pay-runs/{run_id}/` | payroll batches; DELETE cancels a draft |
| POST | `organizations/{id}/pay-runs/{run_id}/payslips/` | add a line to a draft run, `{worker_id, amount, type}` (e.g. an `ALLOWANCE` on top of the salary) |
| POST | `organizations/{id}/pay-runs/{run_id}/{submit\|approve\|reject}/` | send, approve or reject a pay run |
| GET | `payslips/` | a worker's own pay from every business: pay-run lines and one-off salaries, bonuses... (`status` is `PAID` or `REVERSED`) |
| POST | `worker-invitations/preview/` , `worker-invitations/accept/` | `{code}` from the invitation SMS/email (any case, dash optional): who it's from; accept it to be paid by that business into your own wallet. 30 codes an hour |
| GET/POST | `employers/` , `employers/join/` | the businesses you work for or asked to join; `{code}` asks to join with a business's join code (typed or scanned), and the business approves |
| POST | `employers/{worker_id}/leave/` | stop working for a business; your FluxPay account and pay history stay |

Outside `/api/v1/`: `GET /health/` (public), `POST /hooks/<rail>/<token>/` (payment provider callbacks), and the pages email links open: `/reset-password`, `/join`, `/join-business` (public).

Transfers run in one database transaction with row locks taken in a fixed order (no deadlocks), a non-negative balance constraint, a per-user idempotency key, a per-transfer limit and a 20/min throttle. Every transfer writes a DEBIT and a CREDIT ledger line sharing one reference.

## Git workflow

- Only two long-lived branches exist on the remote: `main` — releasable, and `develop` — integration.
- All changes are committed and pushed to `develop`; `develop` is merged into `main` through a pull request once CI passes. Nothing is pushed directly to `main`.
- Commits are small and descriptive (`feat(transfer): …`, `fix(network): …`, `docs: …`).

## CI/CD

| Workflow | Runs on | Does |
|---|---|---|
| `backend.yml` | push/PR to `main`/`develop`, `v*` tags | migrations check, `check --deploy`, tests on PostgreSQL, Docker build. Publishes `ghcr.io/fleur41/fluxpay-api` from `main` (`latest`, `sha-…`) and tags (`1.2.3`, `1.2`) |
| `android.yml` | push/PR to `main`/`develop` | unit tests, dev debug APK, prod release build (debug-signed) |
| `android-release.yml` | `v*.*.*` tags on `main` | unit tests, signed prod APK + AAB, GitHub Release with checksums |

Releasing: merge `develop` into `main` through a PR, then tag the merge commit on `main`:

```bash
git checkout main && git pull
git tag v1.0.1 && git push origin v1.0.1
```

The tag sets `versionName` (`1.0.1`) and `versionCode` (`major*10000 + minor*100 + patch` = `10001`).

The release workflow needs these repository secrets (Settings → Secrets and variables → Actions) and fails rather than ship a debug-signed build without them:

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | `base64 -i android/fluxpay-release.jks` |
| `ANDROID_KEYSTORE_PASSWORD` | keystore password |
| `ANDROID_KEY_ALIAS` | key alias (`fluxpay`) |
| `ANDROID_KEY_PASSWORD` | key password |

Pull the API image with `docker pull ghcr.io/fleur41/fluxpay-api:latest`. The package is private by default; make it public or `docker login ghcr.io` with a token that has `read:packages`.

## Upgrading dependency versions

The catalog in `android/gradle/libs.versions.toml` pins Kotlin 2.0, AGP 8.7 and the Compose BOM; the original 2023 versions from the brief (Kotlin 1.9 / AGP 8.2) were moved up so Room, Hilt and Moshi can all use KSP and Compose can use the Kotlin compose compiler plugin. Android Studio's “Upgrade Assistant” can move them further.
