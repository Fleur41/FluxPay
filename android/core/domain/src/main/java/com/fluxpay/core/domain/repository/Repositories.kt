package com.fluxpay.core.domain.repository

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.core.domain.model.DownloadedStatement
import com.fluxpay.core.domain.model.NotificationSettings
import com.fluxpay.core.domain.model.PlatformConfig
import com.fluxpay.core.domain.model.Recipient
import com.fluxpay.core.domain.model.StatementFormat
import com.fluxpay.core.domain.model.StatementPeriod
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionFilter
import com.fluxpay.core.domain.model.TransferReceipt
import com.fluxpay.core.domain.model.TransferRequest
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.model.UserPreferences
import java.math.BigDecimal
import java.time.Instant
import kotlinx.coroutines.flow.Flow

interface AuthRepository {
    val isLoggedIn: Flow<Boolean>

    suspend fun login(email: String, password: String): NetworkResult<User>

    suspend fun register(
        fullName: String,
        email: String,
        phoneNumber: String,
        password: String,
        currency: String,
    ): NetworkResult<User>

    /** Revokes the refresh token on the server (best effort) and wipes all local data. */
    suspend fun logout(revokeRemotely: Boolean = true)

    suspend fun requestPasswordReset(email: String): NetworkResult<String>

    suspend fun confirmPasswordReset(uid: String, token: String, newPassword: String): NetworkResult<String>

    fun observeProfile(): Flow<User?>

    suspend fun refreshProfile(): NetworkResult<User>
}

/**
 * Offline-first: `observe*` streams always come from the local Room cache;
 * `refresh*` pulls from Django and writes into the cache, which re-emits.
 */
interface AccountRepository {
    fun observeAccounts(): Flow<List<Account>>

    suspend fun refreshAccounts(): NetworkResult<Unit>

    suspend fun lookupRecipient(accountNumber: String): NetworkResult<Recipient>
}

interface TransactionRepository {
    fun observeTransactions(filter: TransactionFilter = TransactionFilter()): Flow<List<Transaction>>

    fun observeTransaction(id: String): Flow<Transaction?>

    suspend fun refreshTransactions(): NetworkResult<Unit>

    suspend fun refreshTransaction(id: String): NetworkResult<Unit>
}

interface TransferRepository {
    suspend fun send(request: TransferRequest): NetworkResult<TransferReceipt>
}

interface PreferencesRepository {
    val preferences: Flow<UserPreferences>

    suspend fun setCurrency(currency: String)

    suspend fun setThemeMode(mode: ThemeMode)

    suspend fun setHideBalances(hide: Boolean)

    suspend fun clear()
}

interface NotificationSettingsRepository {
    suspend fun get(): NetworkResult<NotificationSettings>

    /** Only the non-null fields change. */
    suspend fun update(emailEnabled: Boolean? = null, smsEnabled: Boolean? = null): NetworkResult<NotificationSettings>
}

interface StatementRepository {
    /** Downloads a statement of the user's main wallet into the app's private cache. */
    suspend fun download(period: StatementPeriod, format: StatementFormat): NetworkResult<DownloadedStatement>

    /** Deletes every downloaded statement (called on sign-out). */
    suspend fun clearDownloads()
}

/** The budget planner's data. Local only: it never leaves the phone and is wiped on sign-out. */
interface BudgetRepository {
    fun observeLines(): Flow<List<BudgetLine>>

    suspend fun save(line: BudgetLine)

    suspend fun delete(id: Long)

    /** Money that left the user's wallets between the two instants (completed debits only). */
    fun observeSpending(from: Instant, to: Instant): Flow<BigDecimal>
}

/** Business rules from the server. `config` replays the cached copy at once, then any refresh. */
interface ConfigRepository {
    val config: Flow<PlatformConfig?>

    suspend fun refresh(): NetworkResult<PlatformConfig>
}
