package com.fluxpay.core.domain.repository

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.BookCategory
import com.fluxpay.core.domain.model.BookEntry
import com.fluxpay.core.domain.model.BooksSummary
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.core.domain.model.Business
import com.fluxpay.core.domain.model.BusinessBalance
import com.fluxpay.core.domain.model.BusinessPayment
import com.fluxpay.core.domain.model.BusinessWallet
import com.fluxpay.core.domain.model.Cashbook
import com.fluxpay.core.domain.model.DownloadedStatement
import com.fluxpay.core.domain.model.Employer
import com.fluxpay.core.domain.model.InvitationPreview
import com.fluxpay.core.domain.model.Invoice
import com.fluxpay.core.domain.model.Invoices
import com.fluxpay.core.domain.model.JoinCode
import com.fluxpay.core.domain.model.LoginResult
import com.fluxpay.core.domain.model.Member
import com.fluxpay.core.domain.model.MfaSetup
import com.fluxpay.core.domain.model.MfaStatus
import com.fluxpay.core.domain.model.MpesaWithdrawal
import com.fluxpay.core.domain.model.MyPayslip
import com.fluxpay.core.domain.model.NotificationSettings
import com.fluxpay.core.domain.model.PayRun
import com.fluxpay.core.domain.model.PayoutMethod
import com.fluxpay.core.domain.model.PlatformConfig
import com.fluxpay.core.domain.model.Recipient
import com.fluxpay.core.domain.model.StatementFormat
import com.fluxpay.core.domain.model.StatementPeriod
import com.fluxpay.core.domain.model.Supplier
import com.fluxpay.core.domain.model.TeamInvitation
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

    suspend fun login(email: String, password: String): NetworkResult<LoginResult>

    /** The second step of signing in: a code from the authenticator app, or a recovery code. */
    suspend fun completeLogin(mfaToken: String, code: String): NetworkResult<User>

    suspend fun mfaStatus(): NetworkResult<MfaStatus>

    suspend fun startMfaSetup(): NetworkResult<MfaSetup>

    /** Turns two-step verification on; returns the recovery codes, shown to the user only this once. */
    suspend fun enableMfa(code: String): NetworkResult<List<String>>

    suspend fun disableMfa(password: String, code: String): NetworkResult<Unit>

    suspend fun newRecoveryCodes(code: String): NetworkResult<List<String>>

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

    /** To the user's own M-Pesa number (on their profile); the server refuses any other. Whole shillings. */
    suspend fun withdrawToMpesa(accountId: String, amount: BigDecimal, idempotencyKey: String): NetworkResult<MpesaWithdrawal>
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
    /**
     * The businesses the user is a member of (owner, admin, finance or viewer), with their cashbook balances,
     * as last refreshed; null until first loaded. Workers aren't members, so for them it's empty.
     */
    fun observeMyBusinesses(): Flow<List<BusinessBalance>?>

    /** The user's own pay as a worker, as last refreshed. */
    fun observeMyPay(): Flow<List<MyPayslip>>

    /** Reloads both. */
    suspend fun refreshMine(): NetworkResult<Unit>

    /** Forgets both, at sign-out. */
    fun clearMine()

    suspend fun businesses(): NetworkResult<List<Business>>

    /** Starts a business with the user as its owner; it has its own wallet. */
    suspend fun createBusiness(name: String, registrationNumber: String): NetworkResult<Business>

    // --- The team: owners, admins, finance and viewers ---

    suspend fun members(businessId: String): NetworkResult<List<Member>>

    /** Pending invitations; owners and admins only. */
    suspend fun teamInvitations(businessId: String): NetworkResult<List<TeamInvitation>>

    /** Emails a link to join with this role. A new invitation to the same address replaces the old one. */
    suspend fun inviteMember(businessId: String, email: String, role: String): NetworkResult<TeamInvitation>

    suspend fun revokeTeamInvitation(businessId: String, invitationId: String): NetworkResult<Unit>

    suspend fun changeRole(businessId: String, memberId: String, role: String): NetworkResult<Member>

    /** Removes someone from the team, or, with the user's own membership, leaves the business. */
    suspend fun removeMember(businessId: String, memberId: String): NetworkResult<Unit>

    /** Accepts an emailed team invitation (the token from its link); returns the business joined. */
    suspend fun acceptTeamInvitation(token: String): NetworkResult<Business>

    suspend fun wallet(businessId: String): NetworkResult<BusinessWallet>

    /** Owners only. */
    suspend fun setApprovalLimit(businessId: String, amount: String): NetworkResult<Business>

    suspend fun workers(businessId: String, search: String? = null): NetworkResult<List<Worker>>

    /**
     * Invites someone to be paid by the business, by phone number (with their name and optionally an email) or by
     * their FluxPay account number. They get a code by SMS/email and join only when they accept it.
     */
    suspend fun inviteWorker(
        businessId: String,
        fullName: String,
        phoneOrAccount: String,
        email: String,
        salary: String,
        jobTitle: String,
    ): NetworkResult<Worker>

    /** Every worker that isn't deactivated: active, invited, asking to join, suspended. */
    suspend fun allWorkers(businessId: String): NetworkResult<List<Worker>>

    /** approve (with salary, job title), decline / suspend (with reason), reactivate, resend-invitation. */
    suspend fun workerAction(
        businessId: String,
        workerId: String,
        action: String,
        salary: String? = null,
        jobTitle: String? = null,
        reason: String? = null,
    ): NetworkResult<Worker>

    suspend fun joinCode(businessId: String): NetworkResult<JoinCode>

    /** enabled = true: a new code (the old one stops working); false: joining by code is switched off. */
    suspend fun setJoinCode(businessId: String, enabled: Boolean): NetworkResult<JoinCode>

    // --- As a worker ---

    suspend fun previewInvitation(code: String): NetworkResult<InvitationPreview>

    suspend fun acceptInvitation(code: String): NetworkResult<Employer>

    /** Asks to join a business with its join code; an owner or admin approves. */
    suspend fun requestToJoin(code: String): NetworkResult<Employer>

    suspend fun myEmployers(): NetworkResult<List<Employer>>

    suspend fun leaveEmployer(employerId: String): NetworkResult<Employer>

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

    // --- Suppliers and payments out of the cashbook ---

    suspend fun suppliers(businessId: String): NetworkResult<List<Supplier>>

    /** kind: SUPPLIER, CONTRACTOR, LANDLORD, UTILITY, SERVICE_PROVIDER, OTHER. `details` keys follow the method. */
    suspend fun addSupplier(
        businessId: String,
        name: String,
        kind: String,
        method: PayoutMethod,
        details: Map<String, String>,
    ): NetworkResult<Supplier>

    suspend fun verifySupplier(businessId: String, supplierId: String): NetworkResult<Supplier>

    suspend fun archiveSupplier(businessId: String, supplierId: String): NetworkResult<Supplier>

    suspend fun businessPayments(businessId: String): NetworkResult<List<BusinessPayment>>

    suspend fun paySupplier(
        businessId: String,
        supplierId: String,
        amount: String,
        note: String,
        idempotencyKey: String,
    ): NetworkResult<BusinessPayment>

    /** approve, reject or cancel. */
    suspend fun businessPaymentAction(businessId: String, paymentId: String, action: String, note: String = ""): NetworkResult<BusinessPayment>

    // --- Bills (payables) and invoices (receivables) ---

    suspend fun invoices(businessId: String, openOnly: Boolean): NetworkResult<Invoices>

    /** isBill: money the business owes a supplier (expense category); otherwise owed to it (income category). */
    suspend fun createInvoice(
        businessId: String,
        isBill: Boolean,
        party: String,
        amount: String,
        categoryId: Int,
        description: String,
        dueDate: String?,
    ): NetworkResult<Invoice>

    /** Cashbook entries that could pay this bill or collect this invoice. */
    suspend fun payableEntries(businessId: String, invoiceId: String): NetworkResult<List<BookEntry>>

    /** Links a cashbook entry (a real payment) to the bill or invoice it pays. */
    suspend fun payInvoice(businessId: String, invoiceId: String, entryId: String): NetworkResult<Invoice>

    suspend fun cancelInvoice(businessId: String, invoiceId: String, reason: String): NetworkResult<Invoice>
}
