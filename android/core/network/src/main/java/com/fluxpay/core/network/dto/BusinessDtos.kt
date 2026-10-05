package com.fluxpay.core.network.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass
import java.math.BigDecimal

// Businesses, payroll and business books (backend: organizations/, payroll/). Dates stay ISO strings ("2026-10-04").

@JsonClass(generateAdapter = true)
data class OrganizationDto(
    val id: String,
    val name: String,
    val status: String,
    @Json(name = "my_role") val role: String? = null,
)

@JsonClass(generateAdapter = true)
data class WorkerDto(
    val id: String,
    val name: String,
    @Json(name = "account_number") val accountNumber: String,
    val currency: String,
    @Json(name = "employee_number") val employeeNumber: String = "",
    @Json(name = "job_title") val jobTitle: String = "",
    // Null only on a join request the business hasn't approved yet.
    val salary: BigDecimal? = null,
    @Json(name = "is_active") val isActive: Boolean = true,
    val status: String = "ACTIVE",
    @Json(name = "status_label") val statusLabel: String = "",
    @Json(name = "status_note") val statusNote: String = "",
    @Json(name = "phone_number") val phoneNumber: String = "",
    val email: String = "",
)

@JsonClass(generateAdapter = true)
data class WorkerActionDto(val salary: String? = null, @Json(name = "job_title") val jobTitle: String? = null, val reason: String? = null)

@JsonClass(generateAdapter = true)
data class JoinCodeDto(val enabled: Boolean, val code: String? = null, val link: String? = null)

@JsonClass(generateAdapter = true)
data class CodeDto(val code: String)

@JsonClass(generateAdapter = true)
data class InvitationPreviewDto(
    val business: String,
    val name: String,
    @Json(name = "job_title") val jobTitle: String = "",
)

/** A worker's own view of a business they work for, are invited to, or asked to join. */
@JsonClass(generateAdapter = true)
data class EmployerDto(
    val id: String,
    val business: String,
    @Json(name = "job_title") val jobTitle: String = "",
    val status: String,
    @Json(name = "status_label") val statusLabel: String,
    @Json(name = "account_number") val accountNumber: String = "",
)

@JsonClass(generateAdapter = true)
data class WorkerCreateDto(
    @Json(name = "full_name") val fullName: String = "",
    val email: String = "",
    @Json(name = "account_number") val accountNumber: String = "",
    @Json(name = "phone_number") val phoneNumber: String = "",
    val salary: String,
    @Json(name = "job_title") val jobTitle: String = "",
    @Json(name = "employee_number") val employeeNumber: String = "",
)

@JsonClass(generateAdapter = true)
data class WorkerPatchDto(val salary: String? = null, @Json(name = "job_title") val jobTitle: String? = null)

@JsonClass(generateAdapter = true)
data class WorkerImportDto(val rows: List<Map<String, String>>)

@JsonClass(generateAdapter = true)
data class ImportErrorDto(val row: Int, val error: String)

@JsonClass(generateAdapter = true)
data class WorkerImportResultDto(val created: Int, val updated: Int, val errors: List<ImportErrorDto>)

@JsonClass(generateAdapter = true)
data class PayslipDto(
    val id: String,
    @Json(name = "worker_name") val workerName: String,
    @Json(name = "account_number") val accountNumber: String,
    @Json(name = "employee_number") val employeeNumber: String = "",
    @Json(name = "job_title") val jobTitle: String = "",
    val amount: BigDecimal,
    val status: String,
    @Json(name = "status_label") val statusLabel: String,
    val reference: String? = null,
    @Json(name = "reversal_reason") val reversalReason: String = "",
)

@JsonClass(generateAdapter = true)
data class PayRunDto(
    val id: String,
    val title: String,
    @Json(name = "pay_date") val payDate: String,
    val status: String,
    @Json(name = "status_label") val statusLabel: String,
    val currency: String,
    val total: BigDecimal,
    @Json(name = "reversed_total") val reversedTotal: BigDecimal,
    @Json(name = "worker_count") val workerCount: Int,
    @Json(name = "reversed_count") val reversedCount: Int,
    @Json(name = "created_by_name") val createdByName: String,
    @Json(name = "decided_by_name") val decidedByName: String? = null,
    @Json(name = "decision_note") val decisionNote: String = "",
    val payslips: List<PayslipDto>? = null,
)

@JsonClass(generateAdapter = true)
data class PayRunCreateDto(val title: String, @Json(name = "pay_date") val payDate: String)

@JsonClass(generateAdapter = true)
data class AmountDto(val amount: String)

@JsonClass(generateAdapter = true)
data class NoteDto(val note: String = "")

@JsonClass(generateAdapter = true)
data class ReasonDto(val reason: String)

@JsonClass(generateAdapter = true)
data class MyPayslipDto(
    val id: String,
    val business: String,
    val title: String,
    @Json(name = "pay_date") val payDate: String,
    val amount: BigDecimal,
    val currency: String,
    val status: String,
    @Json(name = "status_label") val statusLabel: String,
    @Json(name = "reversal_reason") val reversalReason: String = "",
)

@JsonClass(generateAdapter = true)
data class CategoryDto(val id: Int, val code: String, val name: String, val type: String)

@JsonClass(generateAdapter = true)
data class CategoryCreateDto(val name: String, val type: String)

@JsonClass(generateAdapter = true)
data class BookEntryDto(
    val id: String,
    val date: String,
    val direction: String,
    val amount: BigDecimal,
    val counterparty: String = "",
    val description: String = "",
    @Json(name = "source_label") val sourceLabel: String,
    val category: CategoryDto,
    val balance: BigDecimal = BigDecimal.ZERO, // absent when a single entry is returned
)

@JsonClass(generateAdapter = true)
data class CashbookWalletDto(
    @Json(name = "account_number") val accountNumber: String,
    val currency: String,
    val balance: BigDecimal,
)

@JsonClass(generateAdapter = true)
data class CashbookDto(
    val wallet: CashbookWalletDto,
    @Json(name = "opening_balance") val openingBalance: BigDecimal,
    @Json(name = "money_in") val moneyIn: BigDecimal,
    @Json(name = "money_out") val moneyOut: BigDecimal,
    @Json(name = "closing_balance") val closingBalance: BigDecimal,
    val entries: List<BookEntryDto>,
)

@JsonClass(generateAdapter = true)
data class ReclassifyDto(@Json(name = "category_id") val categoryId: Int)

@JsonClass(generateAdapter = true)
data class SummaryLineDto(val code: String = "", val name: String, val amount: BigDecimal)

@JsonClass(generateAdapter = true)
data class SummarySectionDto(val title: String, val lines: List<SummaryLineDto>, val total: BigDecimal)

@JsonClass(generateAdapter = true)
data class IncomeStatementDto(val income: SummarySectionDto, val expenses: SummarySectionDto, val profit: BigDecimal)

@JsonClass(generateAdapter = true)
data class BalanceSheetDto(
    val assets: SummarySectionDto,
    val liabilities: SummarySectionDto,
    val equity: SummarySectionDto,
    val balanced: Boolean,
)

@JsonClass(generateAdapter = true)
data class BooksSummaryDto(
    val currency: String,
    @Json(name = "income_statement") val incomeStatement: IncomeStatementDto,
    @Json(name = "balance_sheet") val balanceSheet: BalanceSheetDto,
)
