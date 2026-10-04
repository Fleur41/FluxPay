package com.fluxpay.core.domain.repository

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.BookCategory
import com.fluxpay.core.domain.model.BooksSummary
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.core.domain.model.Business
import com.fluxpay.core.domain.model.BusinessWallet
import com.fluxpay.core.domain.model.Cashbook
import com.fluxpay.core.domain.model.DownloadedStatement
import com.fluxpay.core.domain.model.MyPayslip
import com.fluxpay.core.domain.model.NotificationSettings
import com.fluxpay.core.domain.model.PayRun
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
import com.fluxpay.core.domain.model.Worker
import com.fluxpay.core.domain.model.WorkerImportResult
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


/** Businesses the user belongs to: workers, payroll and the business's own books. Network only. */
interface BusinessRepository {
    suspend fun businesses(): NetworkResult<List<Business>>

    suspend fun wallet(businessId: String): NetworkResult<BusinessWallet>

    suspend fun workers(businessId: String, search: String? = null): NetworkResult<List<Worker>>

    suspend fun addWorker(
        businessId: String,
        accountOrPhone: String,
        salary: String,
        jobTitle: String,
    ): NetworkResult<Worker>

    suspend fun updateSalary(businessId: String, workerId: String, salary: String): NetworkResult<Worker>

    suspend fun removeWorker(businessId: String, workerId: String): NetworkResult<Unit>

    /** CSV text with a header row: account_number (or phone_number), salary, job_title, employee_number. */
    suspend fun importWorkers(businessId: String, csv: String): NetworkResult<WorkerImportResult>

    suspend fun payRuns(businessId: String): NetworkResult<List<PayRun>>

    suspend fun payRun(businessId: String, runId: String): NetworkResult<PayRun>

    suspend fun createPayRun(businessId: String, title: String, payDate: String): NetworkResult<PayRun>

    suspend fun editPayslip(businessId: String, runId: String, payslipId: String, amount: String): NetworkResult<PayRun>

    suspend fun removePayslip(businessId: String, runId: String, payslipId: String): NetworkResult<PayRun>

    /** action: "submit", "approve" or "reject". */
    suspend fun payRunAction(businessId: String, runId: String, action: String, note: String = ""): NetworkResult<PayRun>

    suspend fun cancelPayRun(businessId: String, runId: String): NetworkResult<PayRun>

    suspend fun reversePayslip(businessId: String, payslipId: String, reason: String): NetworkResult<Unit>

    suspend fun myPayslips(): NetworkResult<List<MyPayslip>>

    suspend fun cashbook(businessId: String, start: String, end: String): NetworkResult<Cashbook>

    suspend fun summary(businessId: String, start: String, end: String): NetworkResult<BooksSummary>

    suspend fun categories(businessId: String): NetworkResult<List<BookCategory>>

    suspend fun reclassify(businessId: String, entryId: String, categoryId: Int): NetworkResult<Unit>
}
