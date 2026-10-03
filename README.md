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
| **Settings** | Profile, preferred currency, theme (system / light / dark), hide balances — all in DataStore |
| **Security** | Encrypted tokens (Android Keystore AES-GCM), 5-minute inactivity timeout, FLAG_SECURE, no backups, HTTPS-only outside dev, R8 |

## Android architecture

```
:app ──────────────► :feature:auth  :feature:dashboard  :feature:transfer  :feature:transactions  :feature:settings
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
docker compose up --build          # API on http://localhost:8000, Postgres on :5432
docker compose exec api python manage.py seed_demo
```

Or without Docker (uses SQLite unless `DATABASE_URL` is set):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo         # prints two demo logins and their account numbers
python manage.py runserver 0.0.0.0:8000
python manage.py test              # 17 API tests
```

Demo users: `amina@fluxpay.dev` and `brian@fluxpay.dev`, password `FluxPay#2026`. New sign-ups get a demo balance of 10,000 in debug (`FLUXPAY_SIGNUP_BONUS`, set to 0 in production).

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

### Release signing

```bash
keytool -genkeypair -v -keystore android/fluxpay-release.jks -alias fluxpay -keyalg RSA -keysize 4096 -validity 10000
cp android/keystore.properties.example android/keystore.properties   # then fill in the passwords
```

Both files are git-ignored. Without them, release builds are signed with the debug key (fine for CI, not for Play).

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
