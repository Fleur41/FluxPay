# FluxPay

A secure, offline-first mobile wallet: an **Android app (Kotlin, Jetpack Compose)** backed by a **Django REST API on PostgreSQL**.
Sign up, see your balances, browse and search your history, and send money to another FluxPay account — confirmed with your fingerprint, face or screen lock.

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
| **Business accounts** | Organizations with members, invitations, one cashbook (wallet) per business, typed payments to workers and suppliers with approval and reversal, payroll, and an audit log (API) |
| **Receive** | Share your name and account number from the dashboard so people can pay you |
| **Settings** | Profile, preferred currency, theme (system / light / dark), hide balances — all in DataStore |
| **Admin dashboard** | Staff back-office at `/admin/`: KPIs, customer balances, wallet top-ups and corrections, business oversight, alerts, audit log and platform rules ([guide](#admin-dashboard)) |
| **Security** | Encrypted tokens (Android Keystore AES-GCM), 5-minute inactivity timeout, FLAG_SECURE, no backups, HTTPS-only outside dev, R8 |

## Android architecture

```
:app ──────────────► :feature:auth  :feature:dashboard  :feature:transfer  :feature:transactions  :feature:budget  :feature:settings
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
| **Active customers** | Customer count, and how many joined in the last 7 days |
| **Transfers today** | Number of transfers since midnight, and the volume per currency |
| **Top-ups today** | Staff top-ups and corrections posted today |
| **Failed transactions (7 days)** | Held payouts that were returned |
| **Customer money held** | Total balance and wallet count per currency (FluxPay's own system accounts excluded) |
| **Needs attention** | Business payments waiting for approval, external payments flagged for review, alerts that failed to send. Each links to the filtered list |
| **Audit log** | Tamper check: confirms no audit record has been altered or removed |
| **Recent top-ups & corrections** | The last six, with who posted them |

Staff only see the panels and menu items their permissions allow. The sidebar shows red counts next to **Business payments**, **Payments** and **Email & SMS alerts** when something is waiting.

### What each screen is for

| Sidebar | Screen | Staff can |
|---|---|---|
| Customers | **People** | Search by email, name or phone; filter by staff, active or join date; deactivate a user |
| | **Wallets** | Look up any wallet by number, owner or business, with balance and status |
| Money | **Top-ups & corrections** | Add money to a wallet or take it back (see below) |
| | **Transactions** | Every ledger line, filterable by type, category, status and date; search by reference |
| | **Transfers** | Every customer-to-customer transfer |
| Businesses | **Businesses** | Suspend or reactivate a business; see its members and approval threshold |
| | **Business payments** | Every payment out of a business cashbook (salaries, allowances, supplier payments...) with its type, status and reference. Approving is done by the business's own approvers in the app, not by staff |
| | **Invitations** | Pending, accepted and expired invitations |
| External payments | **Payments** | Deposits and withdrawals through payment providers; filter **Needs review** |
| | **Provider callbacks** | Raw callbacks received from providers, and what happened to each |
| Alerts & compliance | **Email & SMS alerts** | Every alert sent, filterable by channel, event and status (use **Failed** to find problems) |
| | **Audit log** | Who did what and when, across the app and the admin |
| Settings | **Platform rules** | Default currency, statement range, invitation expiry, app inactivity timeout, budget guideline |
| | **Currencies & limits** | Enable or disable currencies; set per-transaction minimum and maximum and the signup bonus |
| | **Staff groups** | Roles for staff members (see below) |

Wallets, transactions, transfers, payments, alerts and the audit log are **view-only**: money only moves through the app's services, so staff can't edit or delete ledger records. Businesses can't be created or deleted here either; customers create them in the app.

### Top up or correct a wallet

Use this for cash a customer paid in at an office, or to fix a mistake.

1. Go to **Money → Top-ups & corrections → Add**.
2. Pick the wallet, then choose **Top-up (add money)** or **Correction (take money back)**.
3. Enter the amount and a reason of at least 10 characters, e.g. *"Cash deposited at the Nairobi office, receipt 1042"*.
4. Save. The wallet changes immediately and the customer gets an email/SMS alert.

Rules:
- The currency's per-transaction limits apply, which guards against an extra zero.
- A correction can't take a wallet below zero.
- Adjustments can't be edited or deleted. To undo one, post the opposite adjustment.
- Every adjustment is double-entry against a **Manual adjustments** system account, so the ledger always balances, and it appears in the customer's history as *Adjustment by FluxPay*.

### Change business rules

- **Settings → Platform rules:** There is one settings record; the link opens it directly. The budget guideline's three percentages must add up to 100.
- **Settings → Currencies & limits:** Edit a currency's limits or signup bonus, or untick **Enabled** to stop new use. Currencies can't be deleted, because wallets refer to them. Keep the signup bonus at 0 unless you're running a promotion.

Changes apply straight away: the app reads them from `GET /api/v1/config/` the next time it loads. Each change is written to the audit log with the old and new values.

### Give staff access

Don't give everyone superuser. Instead:

1. **Settings → Staff groups → Add**, e.g. *Support* (view permissions on people, wallets, transactions, alerts) or *Finance* (add **Can top up or correct customer wallets**, plus view on adjustments and wallets).
2. **Customers → People**, open the person, tick **Staff status**, and add them to the group. Leave **Superuser status** off.

Only users with the **Can top up or correct customer wallets** permission can post adjustments.

### Production notes

- The admin's styles are served by the API itself (WhiteNoise); the Docker image runs `collectstatic` on start, so there is nothing else to host.
- Create the first superuser on the server with `docker run … ghcr.io/fleur41/fluxpay-api python manage.py createsuperuser`, or the equivalent for your host.
- `/admin/` is public on the internet. Use strong passwords, and consider limiting it by IP at your proxy.

## API

All endpoints are under `/api/v1/` and use `Authorization: Bearer <access>` unless marked public. Errors always look like `{"error": {"code": "...", "message": "...", "details": {...}}}`.

| Method | Path | |
|---|---|---|
| POST | `auth/register/` | public — creates user + wallet, returns tokens |
| POST | `auth/login/` | public — `{email, password}` → `{access, refresh, user}` |
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
| GET | `payments/` , `payments/{id}/` | external deposits and withdrawals |
| GET/POST | `organizations/` | your businesses; create one |
| GET/PATCH | `organizations/{id}/` | one business |
| GET, PATCH/DELETE | `organizations/{id}/members/` , `…/members/{member_id}/` | members and their roles |
| GET/POST, DELETE | `organizations/{id}/invitations/` , `…/invitations/{invitation_id}/` | invite by email; revoke |
| POST | `invitations/accept/` | join a business with an invitation token |
| GET | `organizations/{id}/accounts/` , `…/transactions/` , `…/statements/` , `…/audit-events/` | the business cashbook (its one wallet), history, statements and audit log |
| GET/POST | `organizations/{id}/payments/?status=&type=&worker=&pay_run=` | every payment out of the cashbook (`pay_run=none`: only one-off payments). POST `{type, worker_id \| destination_account_number, amount, note, books_category?, idempotency_key}`; `type` is `SALARY`, `ALLOWANCE`, `BONUS`, `COMMISSION`, `OTHER_WORKER` (need `worker_id`), or `SUPPLIER`, `VENDOR`, `CONTRACTOR`, `EXPENSE`, `OTHER` (need an account number) |
| POST | `organizations/{id}/payments/{payment_id}/{approve\|reject\|cancel}/` | decide on a payment waiting for approval (`{note}`) |
| POST | `organizations/{id}/payments/{payment_id}/reverse/` | take back a paid payment, `{reason}`; owners and admins, within the reversal window |
| GET/POST | `organizations/{id}/pay-runs/` , `…/pay-runs/{run_id}/` | payroll batches; DELETE cancels a draft |
| POST | `organizations/{id}/pay-runs/{run_id}/payslips/` | add a line to a draft run, `{worker_id, amount, type}` (e.g. an `ALLOWANCE` on top of the salary) |
| POST | `organizations/{id}/pay-runs/{run_id}/{submit\|approve\|reject}/` | send, approve or reject a pay run |
| GET | `payslips/` | a worker's own pay from every business: pay-run lines and one-off salaries, bonuses... (`status` is `PAID` or `REVERSED`) |

Outside `/api/v1/`: `GET /health/` (public) and `POST /hooks/<rail>/<token>/` (payment provider callbacks).

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
