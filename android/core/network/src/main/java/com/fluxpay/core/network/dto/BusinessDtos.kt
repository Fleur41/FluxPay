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
    @Json(name = "approval_threshold") val approvalThreshold: BigDecimal = BigDecimal.ZERO,
)

@JsonClass(generateAdapter = true)
data class OrganizationPatchDto(@Json(name = "approval_threshold") val approvalThreshold: String)

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
    @Json(name = "approval_threshold") val approvalThreshold: BigDecimal? = null,
    @Json(name = "wallet_balance") val walletBalance: BigDecimal? = null,
    @Json(name = "other_approvers") val otherApprovers: List<String>? = null,
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

// --- The business's team: owners, admins, finance and viewers (backend: organizations/) ---------

@JsonClass(generateAdapter = true)
data class OrganizationCreateDto(
    val name: String,
    @Json(name = "registration_number") val registrationNumber: String = "",
)

@JsonClass(generateAdapter = true)
data class MemberDto(
    val id: String,
    val email: String,
    @Json(name = "full_name") val fullName: String = "",
    val role: String,
)

@JsonClass(generateAdapter = true)
data class TeamInvitationDto(
    val id: String,
    val email: String,
    val role: String,
    @Json(name = "invited_by") val invitedBy: String = "",
    @Json(name = "expires_at") val expiresAt: String,
)

@JsonClass(generateAdapter = true)
data class TeamInviteDto(val email: String, val role: String)

@JsonClass(generateAdapter = true)
data class RoleDto(val role: String)

@JsonClass(generateAdapter = true)
data class TokenDto(val token: String)

// --- Bills (payables) and invoices (receivables) (backend: accounting/invoices.py) -----------------

@JsonClass(generateAdapter = true)
data class InvoicePaymentDto(
    val date: String,
    val amount: BigDecimal,
    val reference: String = "",
    val counterparty: String = "",
)

@JsonClass(generateAdapter = true)
data class InvoiceDto(
    val id: String,
    val kind: String,
    val number: String,
    val party: String,
    val description: String = "",
    val category: CategoryDto,
    val amount: BigDecimal,
    @Json(name = "paid_amount") val paidAmount: BigDecimal,
    val outstanding: BigDecimal,
    @Json(name = "issue_date") val issueDate: String,
    @Json(name = "due_date") val dueDate: String? = null,
    @Json(name = "is_overdue") val isOverdue: Boolean = false,
    val status: String,
    @Json(name = "status_label") val statusLabel: String,
    val payments: List<InvoicePaymentDto> = emptyList(),
)

@JsonClass(generateAdapter = true)
data class InvoiceTotalsDto(
    val payable: BigDecimal,
    val receivable: BigDecimal,
    @Json(name = "payable_overdue") val payableOverdue: BigDecimal,
    @Json(name = "receivable_overdue") val receivableOverdue: BigDecimal,
)

@JsonClass(generateAdapter = true)
data class InvoiceListDto(val currency: String, val totals: InvoiceTotalsDto, val results: List<InvoiceDto>)

@JsonClass(generateAdapter = true)
data class InvoiceCreateDto(
    val kind: String,
    val party: String,
    val amount: String,
    @Json(name = "category_id") val categoryId: Int,
    val description: String = "",
    @Json(name = "due_date") val dueDate: String? = null,
)

@JsonClass(generateAdapter = true)
data class InvoicePayDto(@Json(name = "entry_id") val entryId: String)

// --- Suppliers (saved beneficiaries) and payments out of the cashbook (backend: organizations/) -----

@JsonClass(generateAdapter = true)
data class BeneficiaryDto(
    val id: String,
    val name: String,
    val kind: String,
    @Json(name = "kind_label") val kindLabel: String,
    val method: String,
    @Json(name = "method_label") val methodLabel: String,
    /** Masked (•••• 1234) for members who can't manage suppliers. */
    val details: Map<String, String> = emptyMap(),
    @Json(name = "is_verified") val isVerified: Boolean,
    @Json(name = "verified_by") val verifiedBy: String? = null,
    @Json(name = "details_changed_by") val detailsChangedBy: String? = null,
)

@JsonClass(generateAdapter = true)
data class BusinessPaymentDto(
    val id: String,
    val reference: String,
    @Json(name = "type_label") val typeLabel: String,
    val status: String,
    @Json(name = "status_label") val statusLabel: String,
    val amount: BigDecimal,
    val currency: String,
    @Json(name = "recipient_name") val recipientName: String = "",
    @Json(name = "beneficiary_id") val beneficiaryId: String? = null,
    val note: String = "",
    @Json(name = "created_by") val createdBy: String = "",
    @Json(name = "decided_by") val decidedBy: String? = null,
    @Json(name = "failure_reason") val failureReason: String? = null,
    @Json(name = "created_at") val createdAt: String,
    @Json(name = "payout_method") val payoutMethod: String? = null,
)

@JsonClass(generateAdapter = true)
data class BusinessPaymentCreateDto(
    @Json(name = "beneficiary_id") val beneficiaryId: String,
    val amount: String,
    val note: String = "",
    @Json(name = "idempotency_key") val idempotencyKey: String,
)
