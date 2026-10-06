package com.fluxpay.core.data.repository

import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.result.map
import com.fluxpay.core.domain.model.BookCategory
import com.fluxpay.core.domain.model.BookEntry
import com.fluxpay.core.domain.model.BooksSummary
import com.fluxpay.core.domain.model.Business
import com.fluxpay.core.domain.model.BusinessBalance
import com.fluxpay.core.domain.model.BusinessPayment
import com.fluxpay.core.domain.model.BusinessWallet
import com.fluxpay.core.domain.model.Cashbook
import com.fluxpay.core.domain.model.Employer
import com.fluxpay.core.domain.model.InvitationPreview
import com.fluxpay.core.domain.model.Invoice
import com.fluxpay.core.domain.model.InvoiceTotals
import com.fluxpay.core.domain.model.Invoices
import com.fluxpay.core.domain.model.JoinCode
import com.fluxpay.core.domain.model.Member
import com.fluxpay.core.domain.model.MyPayslip
import com.fluxpay.core.domain.model.PayRun
import com.fluxpay.core.domain.model.PayRunStatus
import com.fluxpay.core.domain.model.PayoutMethod
import com.fluxpay.core.domain.model.Payslip
import com.fluxpay.core.domain.model.SummaryLine
import com.fluxpay.core.domain.model.SummarySection
import com.fluxpay.core.domain.model.Supplier
import com.fluxpay.core.domain.model.TeamInvitation
import com.fluxpay.core.domain.model.Worker
import com.fluxpay.core.domain.model.WorkerImportResult
import com.fluxpay.core.domain.model.WorkerStatus
import com.fluxpay.core.domain.repository.BusinessRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.dto.AmountDto
import com.fluxpay.core.network.dto.BeneficiaryDto
import com.fluxpay.core.network.dto.BusinessPaymentCreateDto
import com.fluxpay.core.network.dto.BusinessPaymentDto
import com.fluxpay.core.network.dto.CategoryDto
import com.fluxpay.core.network.dto.CodeDto
import com.fluxpay.core.network.dto.EmployerDto
import com.fluxpay.core.network.dto.InvoiceCreateDto
import com.fluxpay.core.network.dto.InvoiceDto
import com.fluxpay.core.network.dto.InvoicePayDto
import com.fluxpay.core.network.dto.JoinCodeDto
import com.fluxpay.core.network.dto.NoteDto
import com.fluxpay.core.network.dto.OrganizationCreateDto
import com.fluxpay.core.network.dto.OrganizationDto
import com.fluxpay.core.network.dto.OrganizationPatchDto
import com.fluxpay.core.network.dto.PayRunCreateDto
import com.fluxpay.core.network.dto.PayRunDto
import com.fluxpay.core.network.dto.ReasonDto
import com.fluxpay.core.network.dto.ReclassifyDto
import com.fluxpay.core.network.dto.RoleDto
import com.fluxpay.core.network.dto.SummarySectionDto
import com.fluxpay.core.network.dto.TeamInvitationDto
import com.fluxpay.core.network.dto.TeamInviteDto
import com.fluxpay.core.network.dto.TokenDto
import com.fluxpay.core.network.dto.WorkerActionDto
import com.fluxpay.core.network.dto.WorkerCreateDto
import com.fluxpay.core.network.dto.WorkerDto
import com.fluxpay.core.network.dto.WorkerImportDto
import com.fluxpay.core.network.dto.WorkerPatchDto
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

@Singleton
class BusinessRepositoryImpl @Inject constructor(
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : BusinessRepository {

    private suspend fun <T> call(block: suspend () -> T): NetworkResult<T> = withContext(io) { apiCaller(block) }

    // In memory only: refreshed at sign-in and on Home, forgotten at sign-out.
    private val myBusinesses = MutableStateFlow<List<BusinessBalance>?>(null)
    private val myPay = MutableStateFlow<List<MyPayslip>>(emptyList())

    override fun observeMyBusinesses(): Flow<List<BusinessBalance>?> = myBusinesses.asStateFlow()

    override fun observeMyPay(): Flow<List<MyPayslip>> = myPay.asStateFlow()

    override suspend fun refreshMine(): NetworkResult<Unit> = coroutineScope {
        val pay = async { myPayslips() }
        val businesses = businesses()
        if (businesses is NetworkResult.Success) {
            // A cashbook that fails to load still lists its business (without a balance) rather than hiding it.
            myBusinesses.value = businesses.data
                .map { business -> async { BusinessBalance(business, (wallet(business.id) as? NetworkResult.Success)?.data) } }
                .awaitAll()
        }
        val payResult = pay.await()
        if (payResult is NetworkResult.Success) myPay.value = payResult.data
        listOf(businesses, payResult).filterIsInstance<NetworkResult.Error>().firstOrNull() ?: NetworkResult.Success(Unit)
    }

    override fun clearMine() {
        myBusinesses.value = null
        myPay.value = emptyList()
    }

    override suspend fun businesses() = call { api.organizations() }.map { list -> list.map { it.toDomain() } }

    override suspend fun setApprovalLimit(businessId: String, amount: String) =
        call { api.updateOrganization(businessId, OrganizationPatchDto(amount.replace(",", "").trim())) }.map { it.toDomain() }

    private fun OrganizationDto.toDomain() = Business(id, name, role.orEmpty(), status == "ACTIVE", approvalThreshold)

    override suspend fun createBusiness(name: String, registrationNumber: String) =
        call { api.createOrganization(OrganizationCreateDto(name.trim(), registrationNumber.trim())) }.map { it.toDomain() }

    override suspend fun members(businessId: String) = call { api.members(businessId) }.map { list ->
        list.map { Member(it.id, it.email, it.fullName, it.role) }
    }

    override suspend fun teamInvitations(businessId: String) = call { api.teamInvitations(businessId) }.map { list ->
        list.map { it.toDomain() }
    }

    override suspend fun inviteMember(businessId: String, email: String, role: String) =
        call { api.inviteMember(businessId, TeamInviteDto(email.trim(), role)) }.map { it.toDomain() }

    override suspend fun revokeTeamInvitation(businessId: String, invitationId: String) =
        call { api.revokeTeamInvitation(businessId, invitationId) }.map { }

    override suspend fun changeRole(businessId: String, memberId: String, role: String) =
        call { api.changeRole(businessId, memberId, RoleDto(role)) }.map { Member(it.id, it.email, it.fullName, it.role) }

    override suspend fun removeMember(businessId: String, memberId: String) =
        call { api.removeMember(businessId, memberId) }.map { }

    override suspend fun acceptTeamInvitation(token: String) =
        call { api.acceptTeamInvitation(TokenDto(token.trim())) }.map { it.toDomain() }

    private fun TeamInvitationDto.toDomain() = TeamInvitation(id, email, role, invitedBy, expiresAt.take(10))

    override suspend fun wallet(businessId: String) = call { api.organizationAccounts(businessId) }.map { accounts ->
        accounts.first().let { BusinessWallet(it.id, it.accountNumber, it.currency, it.balance) }
    }

    /** Every page: a business may have hundreds of workers. */
    override suspend fun workers(businessId: String, search: String?) = call {
        val all = mutableListOf<WorkerDto>()
        var page = 1
        do {
            val result = api.workers(businessId, page, search?.takeIf { it.isNotBlank() })
            all += result.results
            page++
        } while (result.next != null)
        all
    }.map { list -> list.map { it.toDomain() } }

    override suspend fun inviteWorker(
        businessId: String,
        fullName: String,
        phoneOrAccount: String,
        email: String,
        salary: String,
        jobTitle: String,
    ) = call {
        val digits = phoneOrAccount.filter { it.isDigit() || it == '+' }
        // FluxPay account numbers are 10 digits and never start with 0; phone numbers do (07..., +254...).
        val isAccount = digits.length == 10 && !digits.startsWith("0")
        api.addWorker(
            businessId,
            WorkerCreateDto(
                fullName = fullName.trim(),
                email = email.trim(),
                accountNumber = if (isAccount) digits else "",
                phoneNumber = if (isAccount) "" else phoneOrAccount.trim(),
                salary = salary,
                jobTitle = jobTitle,
            ),
        )
    }.map { it.toDomain() }

    override suspend fun allWorkers(businessId: String) = call {
        val all = mutableListOf<WorkerDto>()
        var page = 1
        do {
            val result = api.workers(businessId, page, active = "all")
            all += result.results
            page++
        } while (result.next != null)
        all.filter { it.status != "DEACTIVATED" } // people who left are history, not the register
    }.map { list -> list.map { it.toDomain() } }

    override suspend fun workerAction(
        businessId: String,
        workerId: String,
        action: String,
        salary: String?,
        jobTitle: String?,
        reason: String?,
    ) = call { api.workerAction(businessId, workerId, action, WorkerActionDto(salary, jobTitle, reason)) }.map { it.toDomain() }

    override suspend fun joinCode(businessId: String) = call { api.joinCode(businessId) }.map { it.toDomain() }

    override suspend fun setJoinCode(businessId: String, enabled: Boolean) = call {
        if (enabled) api.newJoinCode(businessId) else api.disableJoinCode(businessId)
    }.map { it.toDomain() }

    override suspend fun previewInvitation(code: String) =
        call { api.previewInvitation(CodeDto(code)) }.map { InvitationPreview(it.business, it.name, it.jobTitle) }

    override suspend fun acceptInvitation(code: String) = call { api.acceptInvitation(CodeDto(code)) }.map { it.toDomain() }

    override suspend fun requestToJoin(code: String) = call { api.requestToJoin(CodeDto(code)) }.map { it.toDomain() }

    override suspend fun myEmployers() = call { api.myEmployers() }.map { list -> list.map { it.toDomain() } }

    override suspend fun leaveEmployer(employerId: String) = call { api.leaveEmployer(employerId) }.map { it.toDomain() }

    override suspend fun updateSalary(businessId: String, workerId: String, salary: String) =
        call { api.updateWorker(businessId, workerId, WorkerPatchDto(salary = salary)) }.map { it.toDomain() }

    override suspend fun removeWorker(businessId: String, workerId: String) =
        call { api.removeWorker(businessId, workerId) }.map { }

    override suspend fun importWorkers(businessId: String, csv: String) = call {
        api.importWorkers(businessId, WorkerImportDto(parseCsv(csv)))
    }.map { result -> WorkerImportResult(result.created, result.updated, result.errors.map { "Row ${it.row}: ${it.error}" }) }

    override suspend fun payRuns(businessId: String) = call { api.payRuns(businessId).results }.map { it.map { run -> run.toDomain() } }

    override suspend fun payRun(businessId: String, runId: String) = call { api.payRun(businessId, runId) }.map { it.toDomain() }

    override suspend fun createPayRun(businessId: String, title: String, payDate: String) =
        call { api.createPayRun(businessId, PayRunCreateDto(title, payDate)) }.map { it.toDomain() }

    override suspend fun editPayslip(businessId: String, runId: String, payslipId: String, amount: String) =
        call { api.editPayslip(businessId, runId, payslipId, AmountDto(amount)) }.map { it.toDomain() }

    override suspend fun removePayslip(businessId: String, runId: String, payslipId: String) =
        call { api.removePayslip(businessId, runId, payslipId) }.map { it.toDomain() }

    override suspend fun payRunAction(businessId: String, runId: String, action: String, note: String) =
        call { api.payRunAction(businessId, runId, action, NoteDto(note)) }.map { it.toDomain() }

    override suspend fun cancelPayRun(businessId: String, runId: String) =
        call { api.cancelPayRun(businessId, runId) }.map { it.toDomain() }

    override suspend fun reversePayslip(businessId: String, payslipId: String, reason: String) =
        call { api.reversePayslip(businessId, payslipId, ReasonDto(reason)) }.map { }

    override suspend fun myPayslips() = call { api.myPayslips().results }.map { list ->
        list.map {
            MyPayslip(it.id, it.business, it.title, it.payDate, it.amount, it.currency, it.statusLabel,
                it.status == "REVERSED", it.reversalReason)
        }
    }

    override suspend fun cashbook(businessId: String, start: String, end: String) = call { api.cashbook(businessId, start, end) }.map { dto ->
        Cashbook(
            accountNumber = dto.wallet.accountNumber,
            currency = dto.wallet.currency,
            opening = dto.openingBalance,
            moneyIn = dto.moneyIn,
            moneyOut = dto.moneyOut,
            closing = dto.closingBalance,
            entries = dto.entries.map {
                BookEntry(it.id, it.date, it.direction == "IN", it.amount, it.counterparty, it.description, it.sourceLabel,
                    it.category.toDomain(), it.balance)
            },
        )
    }

    override suspend fun summary(businessId: String, start: String, end: String) = call { api.booksSummary(businessId, start, end) }.map {
        BooksSummary(
            currency = it.currency,
            income = it.incomeStatement.income.toDomain(),
            expenses = it.incomeStatement.expenses.toDomain(),
            profit = it.incomeStatement.profit,
            assets = it.balanceSheet.assets.toDomain(),
            liabilities = it.balanceSheet.liabilities.toDomain(),
            equity = it.balanceSheet.equity.toDomain(),
            balanced = it.balanceSheet.balanced,
        )
    }

    override suspend fun suppliers(businessId: String) = call { api.beneficiaries(businessId).results }.map { list ->
        list.map { it.toDomain() }
    }

    override suspend fun addSupplier(
        businessId: String,
        name: String,
        kind: String,
        method: PayoutMethod,
        details: Map<String, String>,
    ) = call {
        api.addBeneficiary(businessId, mapOf("name" to name.trim(), "kind" to kind, "method" to method.name) +
            details.mapValues { it.value.trim() })
    }.map { it.toDomain() }

    override suspend fun verifySupplier(businessId: String, supplierId: String) =
        call { api.verifyBeneficiary(businessId, supplierId) }.map { it.toDomain() }

    override suspend fun archiveSupplier(businessId: String, supplierId: String) =
        call { api.archiveBeneficiary(businessId, supplierId) }.map { it.toDomain() }

    override suspend fun businessPayments(businessId: String) = call { api.businessPayments(businessId).results }.map { list ->
        list.map { it.toDomain() }
    }

    override suspend fun paySupplier(businessId: String, supplierId: String, amount: String, note: String, idempotencyKey: String) =
        call {
            api.createBusinessPayment(
                businessId, BusinessPaymentCreateDto(supplierId, amount.replace(",", "").trim(), note.trim(), idempotencyKey),
            )
        }.map { it.toDomain() }

    override suspend fun businessPaymentAction(businessId: String, paymentId: String, action: String, note: String) =
        call { api.businessPaymentAction(businessId, paymentId, action, NoteDto(note)) }.map { it.toDomain() }

    private fun BeneficiaryDto.toDomain() = Supplier(
        id, name, kindLabel, methodLabel, details.values.filter { it.isNotBlank() }.joinToString(" · "), isVerified,
        verifiedBy, detailsChangedBy,
    )

    private fun BusinessPaymentDto.toDomain() = BusinessPayment(
        id, reference, recipientName, typeLabel, amount, currency, status, statusLabel, note, createdBy, decidedBy,
        failureReason, createdAt.take(10), payoutMethod,
    )

    override suspend fun invoices(businessId: String, openOnly: Boolean) =
        call { api.invoices(businessId, if (openOnly) "1" else null) }.map { dto ->
            Invoices(
                dto.currency,
                with(dto.totals) { InvoiceTotals(payable, receivable, payableOverdue, receivableOverdue) },
                dto.results.map { it.toDomain() },
            )
        }

    override suspend fun createInvoice(
        businessId: String,
        isBill: Boolean,
        party: String,
        amount: String,
        categoryId: Int,
        description: String,
        dueDate: String?,
    ) = call {
        api.createInvoice(
            businessId,
            InvoiceCreateDto(if (isBill) "BILL" else "INVOICE", party.trim(), amount.replace(",", "").trim(), categoryId,
                description.trim(), dueDate?.takeIf { it.isNotBlank() }),
        )
    }.map { it.toDomain() }

    override suspend fun payableEntries(businessId: String, invoiceId: String) = call { api.payableEntries(businessId, invoiceId) }
        .map { list ->
            list.map {
                BookEntry(it.id, it.date, it.direction == "IN", it.amount, it.counterparty, it.description, it.sourceLabel,
                    it.category.toDomain(), it.balance)
            }
        }

    override suspend fun payInvoice(businessId: String, invoiceId: String, entryId: String) =
        call { api.payInvoice(businessId, invoiceId, InvoicePayDto(entryId)) }.map { it.toDomain() }

    override suspend fun cancelInvoice(businessId: String, invoiceId: String, reason: String) =
        call { api.cancelInvoice(businessId, invoiceId, ReasonDto(reason)) }.map { it.toDomain() }

    private fun InvoiceDto.toDomain() = Invoice(
        id, kind == "BILL", number, party, description, category.toDomain(), amount, paidAmount, outstanding, issueDate,
        dueDate, isOverdue, status, statusLabel, payments.map { Triple(it.date, it.amount, it.counterparty) },
    )

    override suspend fun categories(businessId: String) = call { api.categories(businessId) }.map { it.map { c -> c.toDomain() } }

    override suspend fun reclassify(businessId: String, entryId: String, categoryId: Int) =
        call { api.reclassify(businessId, entryId, ReclassifyDto(categoryId)) }.map { }

    private fun WorkerDto.toDomain() = Worker(
        id, name, accountNumber, currency, employeeNumber, jobTitle, salary, status.toWorkerStatus(), statusLabel,
        statusNote, phoneNumber,
    )

    private fun EmployerDto.toDomain() = Employer(id, business, jobTitle, status.toWorkerStatus(), statusLabel)

    private fun JoinCodeDto.toDomain() = JoinCode(enabled, code, link)

    private fun String.toWorkerStatus() = WorkerStatus.entries.firstOrNull { it.name == this } ?: WorkerStatus.UNKNOWN

    private fun CategoryDto.toDomain() = BookCategory(id, code, name, type)

    private fun SummarySectionDto.toDomain() = SummarySection(title, lines.map { SummaryLine(it.name, it.amount) }, total)

    private fun PayRunDto.toDomain() = PayRun(
        id = id,
        title = title,
        payDate = payDate,
        status = PayRunStatus.entries.firstOrNull { it.name == status } ?: PayRunStatus.UNKNOWN,
        statusLabel = statusLabel,
        currency = currency,
        total = total,
        reversedTotal = reversedTotal,
        workerCount = workerCount,
        reversedCount = reversedCount,
        createdByName = createdByName,
        decidedByName = decidedByName,
        payslips = payslips.orEmpty().map {
            Payslip(it.id, it.workerName, it.accountNumber, it.jobTitle, it.amount, it.status, it.statusLabel, it.reference,
                it.reversalReason)
        },
        approvalThreshold = approvalThreshold ?: java.math.BigDecimal.ZERO,
        walletBalance = walletBalance ?: java.math.BigDecimal.ZERO,
        otherApprovers = otherApprovers.orEmpty(),
    )

    companion object {
        /** A simple CSV reader: header row, comma separated, optional quotes. Headers like "Account Number" work. */
        fun parseCsv(text: String): List<Map<String, String>> {
            val lines = text.lines().map { it.trim() }.filter { it.isNotEmpty() }
            if (lines.isEmpty()) return emptyList()
            val headers = splitCsvLine(lines.first()).map { it.trim().lowercase().replace(' ', '_') }
            return lines.drop(1).map { line ->
                val cells = splitCsvLine(line)
                headers.mapIndexed { i, header -> header to cells.getOrElse(i) { "" }.trim() }.toMap()
            }
        }

        private fun splitCsvLine(line: String): List<String> {
            val cells = mutableListOf<String>()
            val cell = StringBuilder()
            var quoted = false
            for (ch in line) {
                when {
                    ch == '"' -> quoted = !quoted
                    ch == ',' && !quoted -> { cells += cell.toString(); cell.clear() }
                    else -> cell.append(ch)
                }
            }
            cells += cell.toString()
            return cells
        }
    }
}
