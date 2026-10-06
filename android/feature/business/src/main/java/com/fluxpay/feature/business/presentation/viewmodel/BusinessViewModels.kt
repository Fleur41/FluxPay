package com.fluxpay.feature.business.presentation.viewmodel

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.BookCategory
import com.fluxpay.core.domain.model.BookEntry
import com.fluxpay.core.domain.model.BooksSummary
import com.fluxpay.core.domain.model.Business
import com.fluxpay.core.domain.model.BusinessPayment
import com.fluxpay.core.domain.model.BusinessWallet
import com.fluxpay.core.domain.model.Cashbook
import com.fluxpay.core.domain.model.Employer
import com.fluxpay.core.domain.model.InvitationPreview
import com.fluxpay.core.domain.model.Invoice
import com.fluxpay.core.domain.model.Invoices
import com.fluxpay.core.domain.model.JoinCode
import com.fluxpay.core.domain.model.Member
import com.fluxpay.core.domain.model.MyPayslip
import com.fluxpay.core.domain.model.PayRun
import com.fluxpay.core.domain.model.PayRunStatus
import com.fluxpay.core.domain.model.PayoutMethod
import com.fluxpay.core.domain.model.Payslip
import com.fluxpay.core.domain.model.Supplier
import com.fluxpay.core.domain.model.TeamInvitation
import com.fluxpay.core.domain.model.TeamRole
import com.fluxpay.core.domain.model.Worker
import com.fluxpay.core.domain.model.WorkerStatus
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.domain.repository.BusinessRepository
import com.fluxpay.feature.business.navigation.BusinessRoutes
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import javax.inject.Inject
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Common screen state: loading, an error to show, and a one-off message (e.g. "Pay run sent"). */
data class Screen<T>(
    val data: T? = null,
    val loading: Boolean = true,
    val busy: Boolean = false,
    val error: String? = null,
    val message: String? = null,
)

abstract class BaseBusinessViewModel<T>(protected val repository: BusinessRepository) : ViewModel() {
    protected val _state = MutableStateFlow(Screen<T>())
    val state: StateFlow<Screen<T>> = _state.asStateFlow()

    abstract fun load()

    fun messageShown() = _state.update { it.copy(message = null) }

    /** Runs a change on the server, then reloads; failures show as a message, success as `done`. */
    protected fun act(done: String, block: suspend () -> NetworkResult<*>) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = block()) {
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                else -> {
                    _state.update { it.copy(busy = false, message = done) }
                    load()
                }
            }
        }
    }

    protected fun <R> NetworkResult<R>.orFail(): R? = when (this) {
        is NetworkResult.Success -> data
        is NetworkResult.Error -> {
            _state.update { it.copy(loading = false, error = message) }
            null
        }
        NetworkResult.Loading -> null
    }
}

// --- Hub: my businesses and my pay --------------------------------------------------------------

data class Hub(val businesses: List<Business>, val payslips: List<MyPayslip>)

@HiltViewModel
class BusinessHubViewModel @Inject constructor(repository: BusinessRepository) : BaseBusinessViewModel<Hub>(repository) {
    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val businesses = async { repository.businesses() }
            val payslips = async { repository.myPayslips() }
            val list = businesses.await().orFail() ?: return@launch
            val pay = payslips.await().orFail() ?: return@launch
            _state.update { it.copy(data = Hub(list, pay), loading = false) }
        }
    }
}

// --- One business --------------------------------------------------------------------------------

data class BusinessHome(
    val business: Business,
    val wallet: BusinessWallet,
    val workers: Int,
    val payRuns: List<PayRun>,
    /** Workers who asked to join with the join code and are waiting for an owner or admin. */
    val joinRequests: Int = 0,
    /** An owner or admin without two-step verification: they can look, but not act, until it's on. */
    val needsTwoStep: Boolean = false,
    /** What a month's salaries come to, at each active worker's usual pay. */
    val monthlyPayroll: java.math.BigDecimal = java.math.BigDecimal.ZERO,
    /** This month so far; null if it couldn't be loaded (the rest of the page still shows). */
    val month: BooksSummary? = null,
    val monthMoneyIn: java.math.BigDecimal? = null,
    val monthMoneyOut: java.math.BigDecimal? = null,
    val recent: List<BookEntry> = emptyList(),
    val owed: Invoices? = null,
    val paymentsToApprove: Int = 0,
    val suppliersToCheck: Int = 0,
) {
    val waitingForApproval: Int get() = payRuns.count { it.status == PayRunStatus.PENDING_APPROVAL }
}

private suspend fun BusinessRepository.business(id: String): NetworkResult<Business> = when (val all = businesses()) {
    is NetworkResult.Success -> all.data.firstOrNull { it.id == id }?.let { NetworkResult.Success(it) }
        ?: NetworkResult.Error("Business not found.")
    is NetworkResult.Error -> all
    NetworkResult.Loading -> NetworkResult.Loading
}

@HiltViewModel
class BusinessHomeViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
    private val auth: AuthRepository,
) : BaseBusinessViewModel<BusinessHome>(repository) {
    val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val wallet = async { repository.wallet(businessId) }
            val workers = async { repository.allWorkers(businessId) }
            val runs = async { repository.payRuns(businessId) }
            val b = business.await().orFail() ?: return@launch
            val w = wallet.await().orFail() ?: return@launch
            val ws = workers.await().orFail() ?: return@launch
            val rs = runs.await().orFail() ?: return@launch
            val active = ws.count { it.status == WorkerStatus.ACTIVE }
            val requests = ws.count { it.status == WorkerStatus.PENDING_ACTIVATION }
            val mfa = (auth.mfaStatus() as? NetworkResult.Success)?.data
            val needsTwoStep = b.canApprove && mfa != null && mfa.required && !mfa.enabled
            val payroll = ws.filter { it.status == WorkerStatus.ACTIVE }
                .fold(java.math.BigDecimal.ZERO) { sum, worker -> sum + (worker.salary ?: java.math.BigDecimal.ZERO) }
            val home = BusinessHome(b, w, active, rs, requests, needsTwoStep, payroll)
            _state.update { it.copy(data = it.data?.let { old -> extras(old, home) } ?: home, loading = false) }
            loadExtras(home)
        }
    }

    /** The dashboard's figures: optional, so a slow or failing one never blanks the page. */
    private fun extras(from: BusinessHome, into: BusinessHome) = into.copy(
        month = from.month, monthMoneyIn = from.monthMoneyIn, monthMoneyOut = from.monthMoneyOut, recent = from.recent,
        owed = from.owed, paymentsToApprove = from.paymentsToApprove, suppliersToCheck = from.suppliersToCheck,
    )

    private fun loadExtras(home: BusinessHome) {
        viewModelScope.launch {
            val today = LocalDate.now()
            val start = today.withDayOfMonth(1).toString()
            val summary = async { repository.summary(businessId, start, today.toString()) }
            val cashbook = async { repository.cashbook(businessId, start, today.toString()) }
            val owed = async { repository.invoices(businessId, openOnly = true) }
            val payments = async { repository.businessPayments(businessId) }
            val suppliers = async { repository.suppliers(businessId) }
            val book = (cashbook.await() as? NetworkResult.Success)?.data
            val updated = home.copy(
                month = (summary.await() as? NetworkResult.Success)?.data,
                monthMoneyIn = book?.moneyIn,
                monthMoneyOut = book?.moneyOut,
                recent = book?.entries.orEmpty().take(5),
                owed = (owed.await() as? NetworkResult.Success)?.data,
                paymentsToApprove = (payments.await() as? NetworkResult.Success)?.data.orEmpty().count { it.waitingForApproval },
                suppliersToCheck = (suppliers.await() as? NetworkResult.Success)?.data.orEmpty().count { !it.isVerified },
            )
            _state.update { it.copy(data = updated) }
        }
    }

    /** Owners only; the server checks the role and records it in the audit log. */
    fun setApprovalLimit(amount: String) = act("Approval limit changed") { repository.setApprovalLimit(businessId, amount) }
}

// --- Starting a business --------------------------------------------------------------------------

/** Set once the business exists, to open it. */
data class NewBusiness(val createdId: String? = null)

@HiltViewModel
class NewBusinessViewModel @Inject constructor(repository: BusinessRepository) : BaseBusinessViewModel<NewBusiness>(repository) {
    init { _state.update { it.copy(data = NewBusiness(), loading = false) } }

    override fun load() = Unit

    fun create(name: String, registrationNumber: String) {
        if (name.isBlank()) return _state.update { it.copy(message = "Give the business a name.") }
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.createBusiness(name, registrationNumber)) {
                is NetworkResult.Success -> {
                    repository.refreshMine() // the Business tab and Home's business card appear
                    _state.update { it.copy(busy = false, data = NewBusiness(result.data.id)) }
                }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }
}

// --- The team: owners, admins, finance, viewers ----------------------------------------------------

data class Team(
    val business: Business,
    val members: List<Member>,
    /** Loaded for owners and admins only. */
    val invitations: List<TeamInvitation>,
    val myEmail: String,
    /** Set when the user left the business, to go back. */
    val left: Boolean = false,
) {
    fun isMe(member: Member) = member.email.equals(myEmail, ignoreCase = true)

    fun canManage(role: String) = business.manageableRoles.any { it.name == role }
}

@HiltViewModel
class TeamViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
    private val auth: AuthRepository,
) : BaseBusinessViewModel<Team>(repository) {
    private val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val members = async { repository.members(businessId) }
            val b = business.await().orFail() ?: return@launch
            val ms = members.await().orFail() ?: return@launch
            val invitations = if (b.manageableRoles.isEmpty()) emptyList() else repository.teamInvitations(businessId).orFail() ?: return@launch
            val me = auth.observeProfile().first()?.email.orEmpty()
            _state.update { it.copy(data = Team(b, ms, invitations, me), loading = false) }
        }
    }

    fun invite(email: String, role: TeamRole) =
        act("Invitation emailed to ${email.trim()}") { repository.inviteMember(businessId, email, role.name) }

    fun cancelInvitation(invitation: TeamInvitation) =
        act("Invitation to ${invitation.email} cancelled") { repository.revokeTeamInvitation(businessId, invitation.id) }

    fun changeRole(member: Member, role: TeamRole) =
        act("${member.fullName.ifBlank { member.email }} is now ${role.label.lowercase()}") {
            repository.changeRole(businessId, member.id, role.name)
        }

    fun remove(member: Member) =
        act("${member.fullName.ifBlank { member.email }} removed from the team") { repository.removeMember(businessId, member.id) }

    fun leave(me: Member) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.removeMember(businessId, me.id)) {
                is NetworkResult.Success -> {
                    repository.refreshMine()
                    _state.update { it.copy(busy = false, data = it.data?.copy(left = true)) }
                }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }
}

/**
 * Accepting an emailed invitation to a business's team: opened from its link (fluxpay://join-business?token=…),
 * or with the link pasted in.
 */
data class JoinTeam(val link: String = "", val joined: Business? = null)

@HiltViewModel
class JoinTeamViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<JoinTeam>(repository) {
    init {
        _state.update { it.copy(data = JoinTeam(savedState.get<String>(BusinessRoutes.TOKEN).orEmpty()), loading = false) }
    }

    override fun load() = Unit

    fun onLink(link: String) = _state.update { it.copy(data = it.data?.copy(link = link)) }

    fun accept() {
        val token = tokenFrom(_state.value.data?.link.orEmpty())
        if (token.isEmpty()) return _state.update { it.copy(message = "Paste the link from the invitation email.") }
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.acceptTeamInvitation(token)) {
                is NetworkResult.Success -> {
                    repository.refreshMine()
                    _state.update { it.copy(busy = false, data = it.data?.copy(joined = result.data)) }
                }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    companion object {
        /** The whole link from the email, or just its token. */
        fun tokenFrom(text: String): String {
            val trimmed = text.trim()
            return Regex("""[?&]token=([^&\s]+)""").find(trimmed)?.groupValues?.get(1) ?: trimmed
        }
    }
}

// --- Workers -------------------------------------------------------------------------------------

/** The tabs of the workers screen, each a set of statuses. */
enum class WorkerTab(val label: String, val statuses: Set<WorkerStatus>) {
    ACTIVE("Active", setOf(WorkerStatus.ACTIVE)),
    INVITED("Invited", setOf(WorkerStatus.INVITED)),
    REQUESTS("Requests", setOf(WorkerStatus.PENDING_ACTIVATION)),
    SUSPENDED("Suspended", setOf(WorkerStatus.SUSPENDED)),
}

data class Workers(
    val business: Business,
    val workers: List<Worker>,
    val search: String = "",
    val tab: WorkerTab = WorkerTab.ACTIVE,
    /** Loaded for owners and admins only, who run the join code. */
    val joinCode: JoinCode? = null,
) {
    fun count(tab: WorkerTab) = workers.count { it.status in tab.statuses }

    val shown: List<Worker> get() = workers.filter { it.status in tab.statuses }.filter {
        search.isBlank() || it.name.contains(search, ignoreCase = true) || it.accountNumber.startsWith(search) ||
            it.phoneNumber.contains(search) || it.jobTitle.contains(search, ignoreCase = true) ||
            it.employeeNumber.equals(search, ignoreCase = true)
    }
    val active: List<Worker> get() = workers.filter { it.status == WorkerStatus.ACTIVE }
    val monthlyPayroll get() = active.fold(java.math.BigDecimal.ZERO) { sum, w -> sum + (w.salary ?: java.math.BigDecimal.ZERO) }
}

@HiltViewModel
class WorkersViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<Workers>(repository) {
    private val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])
    private val startTab = savedState.get<String>(BusinessRoutes.TAB)?.let { tab -> WorkerTab.entries.firstOrNull { it.name == tab } }

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val workers = async { repository.allWorkers(businessId) }
            val b = business.await().orFail() ?: return@launch
            val ws = workers.await().orFail() ?: return@launch
            val code = if (b.canApprove) (repository.joinCode(businessId) as? NetworkResult.Success)?.data else null
            _state.update {
                val old = it.data
                it.copy(
                    data = Workers(b, ws, old?.search.orEmpty(), old?.tab ?: startTab ?: WorkerTab.ACTIVE, code ?: old?.joinCode),
                    loading = false,
                )
            }
        }
    }

    fun search(text: String) = _state.update { it.copy(data = it.data?.copy(search = text)) }

    fun showTab(tab: WorkerTab) = _state.update { it.copy(data = it.data?.copy(tab = tab)) }

    fun invite(name: String, phoneOrAccount: String, email: String, salary: String, jobTitle: String) =
        act("Invitation sent. They'll appear under Active once they accept.") {
            repository.inviteWorker(businessId, name, phoneOrAccount, email, salary, jobTitle)
        }

    fun changeSalary(worker: Worker, salary: String) =
        act("${worker.name}'s salary updated") { repository.updateSalary(businessId, worker.id, salary) }

    /** Removes an active or suspended worker, or cancels an invitation. Their pay history stays. */
    fun remove(worker: Worker) = act(
        if (worker.status == WorkerStatus.INVITED) "Invitation cancelled" else "${worker.name} removed from payroll",
    ) { repository.removeWorker(businessId, worker.id) }

    fun resend(worker: Worker) = act("Invitation sent again with a new code") {
        repository.workerAction(businessId, worker.id, "resend-invitation")
    }

    fun approve(worker: Worker, salary: String, jobTitle: String) = act("${worker.name} can now be paid") {
        repository.workerAction(businessId, worker.id, "approve", salary = salary, jobTitle = jobTitle)
    }

    fun decline(worker: Worker, reason: String) = act("Request declined") {
        repository.workerAction(businessId, worker.id, "decline", reason = reason)
    }

    fun suspend(worker: Worker, reason: String) = act("${worker.name} suspended: they can't be paid") {
        repository.workerAction(businessId, worker.id, "suspend", reason = reason)
    }

    fun reactivate(worker: Worker) = act("${worker.name} is active again") {
        repository.workerAction(businessId, worker.id, "reactivate")
    }

    fun setJoinCode(enabled: Boolean) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.setJoinCode(businessId, enabled)) {
                is NetworkResult.Success -> _state.update {
                    it.copy(busy = false, data = it.data?.copy(joinCode = result.data),
                        message = if (enabled) "New join code: the old one no longer works" else "Joining by code is off")
                }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun import(csv: String) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.importWorkers(businessId, csv)) {
                is NetworkResult.Success -> {
                    val r = result.data
                    val problems = if (r.errors.isEmpty()) "" else " ${r.errors.size} rows skipped: ${r.errors.take(3).joinToString("; ")}"
                    _state.update { it.copy(busy = false, message = "Invited ${r.created} workers.$problems") }
                    load()
                }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }
}

// --- As a worker: my employers, joining a business ---------------------------------------------------

@HiltViewModel
class EmployersViewModel @Inject constructor(repository: BusinessRepository) : BaseBusinessViewModel<List<Employer>>(repository) {
    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val employers = repository.myEmployers().orFail() ?: return@launch
            _state.update { it.copy(data = employers, loading = false) }
        }
    }

    fun leave(employer: Employer) = act(
        if (employer.status == WorkerStatus.ACTIVE) "You left ${employer.business}" else "Cancelled",
    ) { repository.leaveEmployer(employer.id) }
}

/**
 * One code box for both kinds of code: a personal invitation (from SMS or email) is shown first so the worker
 * can accept it; any other code is taken as a business's join code, and the business is asked to approve.
 */
data class JoinBusiness(
    val code: String = "",
    val invitation: InvitationPreview? = null,
    /** Set once they joined or asked to: what to show, and the employer. */
    val done: Employer? = null,
)

@HiltViewModel
class JoinBusinessViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<JoinBusiness>(repository) {
    init {
        _state.update { it.copy(data = JoinBusiness(), loading = false) }
        // From a link: fluxpay://join-employer?code=... (invitation) or ?business=... (join code, e.g. a QR).
        savedState.get<String>(BusinessRoutes.CODE)?.takeIf { it.isNotBlank() }?.let { onCode(it); submit() }
        savedState.get<String>(BusinessRoutes.JOIN_CODE)?.takeIf { it.isNotBlank() }?.let { onCode(it); requestToJoin() }
    }

    override fun load() = Unit

    fun onCode(code: String) = _state.update { it.copy(data = JoinBusiness(code = code)) }

    /** A scanned QR code holds the business's join link; anything else is treated as a typed code. */
    fun onScanned(raw: String) {
        val uri = runCatching { android.net.Uri.parse(raw) }.getOrNull()
        val business = uri?.takeIf { it.scheme == "fluxpay" }?.getQueryParameter("business")
        val invite = uri?.takeIf { it.scheme == "fluxpay" }?.getQueryParameter("code")
        onCode(business ?: invite ?: raw)
        if (business != null) requestToJoin() else submit()
    }

    fun submit() {
        val code = _state.value.data?.code?.trim().orEmpty()
        if (code.isEmpty()) return
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val preview = repository.previewInvitation(code)) {
                is NetworkResult.Success -> _state.update {
                    it.copy(busy = false, data = it.data?.copy(invitation = preview.data))
                }
                // Not a personal invitation: it may be a business's join code.
                is NetworkResult.Error -> if (preview.httpStatus == 404) join(code) else fail(preview.message)
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun accept() {
        val code = _state.value.data?.code?.trim().orEmpty()
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.acceptInvitation(code)) {
                is NetworkResult.Success -> _state.update { it.copy(busy = false, data = it.data?.copy(done = result.data)) }
                is NetworkResult.Error -> fail(result.message)
                NetworkResult.Loading -> Unit
            }
        }
    }

    private fun requestToJoin() {
        val code = _state.value.data?.code?.trim().orEmpty()
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            join(code)
        }
    }

    private suspend fun join(code: String) {
        when (val result = repository.requestToJoin(code)) {
            is NetworkResult.Success -> _state.update { it.copy(busy = false, data = it.data?.copy(done = result.data)) }
            is NetworkResult.Error -> fail(
                if (result.httpStatus == 404) "That code isn't valid or has expired. Check it, or ask the business for a new one."
                else result.message,
            )
            NetworkResult.Loading -> Unit
        }
    }

    private fun fail(message: String) = _state.update { it.copy(busy = false, message = message) }
}

// --- Suppliers and paying them --------------------------------------------------------------------

data class Suppliers(
    val business: Business,
    val suppliers: List<Supplier>,
    val payments: List<BusinessPayment>,
    val currency: String,
)

/** Saved suppliers (with payout details an owner or admin has checked) and payments to them. */
@HiltViewModel
class SuppliersViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<Suppliers>(repository) {
    private val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val suppliers = async { repository.suppliers(businessId) }
            val payments = async { repository.businessPayments(businessId) }
            val wallet = async { repository.wallet(businessId) }
            val b = business.await().orFail() ?: return@launch
            val ss = suppliers.await().orFail() ?: return@launch
            val ps = payments.await().orFail() ?: return@launch
            val w = wallet.await().orFail() ?: return@launch
            _state.update { it.copy(data = Suppliers(b, ss, ps, w.currency), loading = false) }
        }
    }

    fun add(name: String, kind: String, method: PayoutMethod, details: Map<String, String>) =
        act("$name saved. An owner or admin must check the payout details before the first payment.") {
            repository.addSupplier(businessId, name, kind, method, details)
        }

    fun verify(supplier: Supplier) = act("${supplier.name}'s payout details checked: you can pay them") {
        repository.verifySupplier(businessId, supplier.id)
    }

    fun archive(supplier: Supplier) = act("${supplier.name} removed") { repository.archiveSupplier(businessId, supplier.id) }

    fun pay(supplier: Supplier, amount: String, note: String) {
        val key = java.util.UUID.randomUUID().toString()
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.paySupplier(businessId, supplier.id, amount, note, key)) {
                is NetworkResult.Success -> {
                    val payment = result.data
                    val message = when (payment.status) {
                        "PENDING_APPROVAL" -> "Above the approval limit: it waits for an owner or admin to approve"
                        "PROCESSING" -> "Sent to ${payment.payoutMethod ?: "the provider"}: it shows as paid once confirmed"
                        "FAILED" -> "Payment failed: ${payment.failureReason.orEmpty()}"
                        else -> "Paid ${supplier.name}"
                    }
                    _state.update { it.copy(busy = false, message = message) }
                    load()
                }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun decide(payment: BusinessPayment, action: String, note: String = "") = act(
        when (action) { "approve" -> "Approved: ${payment.recipient} is being paid"; "reject" -> "Rejected"; else -> "Cancelled" },
    ) { repository.businessPaymentAction(businessId, payment.id, action, note) }
}

// --- Pay runs ------------------------------------------------------------------------------------

data class PayRuns(val business: Business, val runs: List<PayRun>, val createdRunId: String? = null)

@HiltViewModel
class PayRunsViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<PayRuns>(repository) {
    val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val runs = async { repository.payRuns(businessId) }
            val b = business.await().orFail() ?: return@launch
            val rs = runs.await().orFail() ?: return@launch
            _state.update { it.copy(data = PayRuns(b, rs), loading = false) }
        }
    }

    /** A draft for every active worker at their usual salary; opens it for review. */
    fun create(title: String) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.createPayRun(businessId, title, LocalDate.now().toString())) {
                is NetworkResult.Success -> _state.update { it.copy(busy = false, data = it.data?.copy(createdRunId = result.data.id)) }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun opened() = _state.update { it.copy(data = it.data?.copy(createdRunId = null)) }

    fun suggestedTitle(): String =
        LocalDate.now().format(DateTimeFormatter.ofPattern("MMMM yyyy", Locale.getDefault())) + " salaries"
}

data class PayRunDetail(val business: Business, val run: PayRun, val search: String = "") {
    val shown: List<Payslip> get() = if (search.isBlank()) run.payslips else run.payslips.filter {
        it.workerName.contains(search, ignoreCase = true) || it.accountNumber.startsWith(search)
    }
}

@HiltViewModel
class PayRunDetailViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<PayRunDetail>(repository) {
    private val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])
    private val runId: String = checkNotNull(savedState[BusinessRoutes.RUN_ID])

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val run = async { repository.payRun(businessId, runId) }
            val b = business.await().orFail() ?: return@launch
            val r = run.await().orFail() ?: return@launch
            _state.update { it.copy(data = PayRunDetail(b, r, it.data?.search.orEmpty()), loading = false) }
        }
    }

    fun search(text: String) = _state.update { it.copy(data = it.data?.copy(search = text)) }

    fun submit() = act("Pay run sent") { repository.payRunAction(businessId, runId, "submit") }

    fun approve(note: String) = act("Approved: everyone has been paid") { repository.payRunAction(businessId, runId, "approve", note) }

    fun reject(note: String) = act("Pay run rejected") { repository.payRunAction(businessId, runId, "reject", note) }

    fun cancel() = act("Pay run cancelled") { repository.cancelPayRun(businessId, runId) }

    fun editAmount(payslip: Payslip, amount: String) =
        act("${payslip.workerName}'s pay changed") { repository.editPayslip(businessId, runId, payslip.id, amount) }

    fun leaveOut(payslip: Payslip) =
        act("${payslip.workerName} left out of this pay run") { repository.removePayslip(businessId, runId, payslip.id) }

    fun reverse(payslip: Payslip, reason: String) =
        act("${payslip.workerName}'s pay was taken back") { repository.reversePayslip(businessId, payslip.id, reason) }
}

// --- Books ---------------------------------------------------------------------------------------

enum class BooksPeriod(val label: String) { THIS_MONTH("This month"), LAST_MONTH("Last month"), THIS_YEAR("This year") }

data class Books(
    val business: Business,
    val period: BooksPeriod,
    val cashbook: Cashbook,
    val summary: BooksSummary,
    val categories: List<BookCategory>,
    /** Bills (we owe) and invoices (owed to us), with totals. */
    val invoices: Invoices,
    val openOnly: Boolean = true,
    /** The cashbook entries that could pay the invoice being paid; null while loading. */
    val payable: List<BookEntry>? = null,
)

@HiltViewModel
class BooksViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<Books>(repository) {
    private val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])
    private var period = BooksPeriod.THIS_MONTH
    private var openOnly = true

    init { load() }

    fun choose(newPeriod: BooksPeriod) {
        period = newPeriod
        load()
    }

    private fun range(): Pair<String, String> {
        val today = LocalDate.now()
        return when (period) {
            BooksPeriod.THIS_MONTH -> today.withDayOfMonth(1) to today
            BooksPeriod.LAST_MONTH -> today.minusMonths(1).withDayOfMonth(1).let { it to it.plusMonths(1).minusDays(1) }
            BooksPeriod.THIS_YEAR -> today.withDayOfYear(1) to today
        }.let { (start, end) -> start.toString() to end.toString() }
    }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null || it.data.period != period, error = null) }
            val (start, end) = range()
            val business = async { repository.business(businessId) }
            val cashbook = async { repository.cashbook(businessId, start, end) }
            val summary = async { repository.summary(businessId, start, end) }
            val categories = async { repository.categories(businessId) }
            val invoices = async { repository.invoices(businessId, openOnly) }
            val b = business.await().orFail() ?: return@launch
            val c = cashbook.await().orFail() ?: return@launch
            val s = summary.await().orFail() ?: return@launch
            val cats = categories.await().orFail() ?: return@launch
            val inv = invoices.await().orFail() ?: return@launch
            _state.update { it.copy(data = Books(b, period, c, s, cats, inv, openOnly), loading = false) }
        }
    }

    fun refile(entry: BookEntry, category: BookCategory) =
        act("Filed under ${category.name}") { repository.reclassify(businessId, entry.id, category.id) }

    fun showOpenOnly(open: Boolean) {
        openOnly = open
        load()
    }

    fun record(isBill: Boolean, party: String, amount: String, category: BookCategory, description: String, dueDate: String?) =
        act(if (isBill) "Bill recorded: it shows as owed until you link its payment" else "Invoice recorded") {
            repository.createInvoice(businessId, isBill, party, amount, category.id, description, dueDate)
        }

    /** Loads the cashbook entries that could pay this bill or collect this invoice. */
    fun findPayments(invoice: Invoice) {
        _state.update { it.copy(data = it.data?.copy(payable = null)) }
        viewModelScope.launch {
            when (val result = repository.payableEntries(businessId, invoice.id)) {
                is NetworkResult.Success -> _state.update { it.copy(data = it.data?.copy(payable = result.data)) }
                is NetworkResult.Error -> _state.update { it.copy(message = result.message, data = it.data?.copy(payable = emptyList())) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun pay(invoice: Invoice, entry: BookEntry) =
        act("${invoice.number}: ${if (invoice.isBill) "payment" else "receipt"} linked") {
            repository.payInvoice(businessId, invoice.id, entry.id)
        }

    fun cancel(invoice: Invoice, reason: String) =
        act("${invoice.number} cancelled") { repository.cancelInvoice(businessId, invoice.id, reason) }
}
