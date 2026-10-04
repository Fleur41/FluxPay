package com.fluxpay.feature.business.presentation.viewmodel

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.BookCategory
import com.fluxpay.core.domain.model.BookEntry
import com.fluxpay.core.domain.model.BooksSummary
import com.fluxpay.core.domain.model.Business
import com.fluxpay.core.domain.model.BusinessWallet
import com.fluxpay.core.domain.model.Cashbook
import com.fluxpay.core.domain.model.MyPayslip
import com.fluxpay.core.domain.model.PayRun
import com.fluxpay.core.domain.model.PayRunStatus
import com.fluxpay.core.domain.model.Payslip
import com.fluxpay.core.domain.model.Worker
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

data class BusinessHome(val business: Business, val wallet: BusinessWallet, val workers: Int, val payRuns: List<PayRun>) {
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
) : BaseBusinessViewModel<BusinessHome>(repository) {
    val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val wallet = async { repository.wallet(businessId) }
            val workers = async { repository.workers(businessId) }
            val runs = async { repository.payRuns(businessId) }
            val b = business.await().orFail() ?: return@launch
            val w = wallet.await().orFail() ?: return@launch
            val ws = workers.await().orFail() ?: return@launch
            val rs = runs.await().orFail() ?: return@launch
            _state.update { it.copy(data = BusinessHome(b, w, ws.size, rs), loading = false) }
        }
    }
}

// --- Workers -------------------------------------------------------------------------------------

data class Workers(val business: Business, val workers: List<Worker>, val search: String = "") {
    val shown: List<Worker> get() = if (search.isBlank()) workers else workers.filter {
        it.name.contains(search, ignoreCase = true) || it.accountNumber.startsWith(search) ||
            it.jobTitle.contains(search, ignoreCase = true) || it.employeeNumber.equals(search, ignoreCase = true)
    }
    val monthlyPayroll get() = workers.fold(java.math.BigDecimal.ZERO) { sum, w -> sum + w.salary }
}

@HiltViewModel
class WorkersViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<Workers>(repository) {
    private val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])

    init { load() }

    override fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.data == null, error = null) }
            val business = async { repository.business(businessId) }
            val workers = async { repository.workers(businessId) }
            val b = business.await().orFail() ?: return@launch
            val ws = workers.await().orFail() ?: return@launch
            _state.update { it.copy(data = Workers(b, ws, it.data?.search.orEmpty()), loading = false) }
        }
    }

    fun search(text: String) = _state.update { it.copy(data = it.data?.copy(search = text)) }

    fun add(accountOrPhone: String, salary: String, jobTitle: String) =
        act("Worker added") { repository.addWorker(businessId, accountOrPhone, salary, jobTitle) }

    fun changeSalary(worker: Worker, salary: String) =
        act("${worker.name}'s salary updated") { repository.updateSalary(businessId, worker.id, salary) }

    fun remove(worker: Worker) = act("${worker.name} removed from payroll") { repository.removeWorker(businessId, worker.id) }

    fun import(csv: String) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true) }
            when (val result = repository.importWorkers(businessId, csv)) {
                is NetworkResult.Success -> {
                    val r = result.data
                    val problems = if (r.errors.isEmpty()) "" else " ${r.errors.size} rows skipped: ${r.errors.take(3).joinToString("; ")}"
                    _state.update { it.copy(busy = false, message = "Imported ${r.created} new, ${r.updated} updated.$problems") }
                    load()
                }
                is NetworkResult.Error -> _state.update { it.copy(busy = false, message = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }
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
)

@HiltViewModel
class BooksViewModel @Inject constructor(
    savedState: SavedStateHandle,
    repository: BusinessRepository,
) : BaseBusinessViewModel<Books>(repository) {
    private val businessId: String = checkNotNull(savedState[BusinessRoutes.BUSINESS_ID])
    private var period = BooksPeriod.THIS_MONTH

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
            val b = business.await().orFail() ?: return@launch
            val c = cashbook.await().orFail() ?: return@launch
            val s = summary.await().orFail() ?: return@launch
            val cats = categories.await().orFail() ?: return@launch
            _state.update { it.copy(data = Books(b, period, c, s, cats), loading = false) }
        }
    }

    fun refile(entry: BookEntry, category: BookCategory) =
        act("Filed under ${category.name}") { repository.reclassify(businessId, entry.id, category.id) }
}
