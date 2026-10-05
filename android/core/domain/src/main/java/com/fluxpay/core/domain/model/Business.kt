package com.fluxpay.core.domain.model

import java.math.BigDecimal

/** A business the user belongs to, with their role in it (OWNER, ADMIN, FINANCE, VIEWER). */
data class Business(val id: String, val name: String, val role: String, val isActive: Boolean) {
    /** Owners, admins and finance prepare pay runs and manage workers. */
    val canPrepare: Boolean get() = role in setOf("OWNER", "ADMIN", "FINANCE")

    /** Owners and admins approve pay runs and take back wrong payments. */
    val canApprove: Boolean get() = role in setOf("OWNER", "ADMIN")

    val roleLabel: String get() = role.lowercase().replaceFirstChar { it.uppercase() }
}

data class BusinessWallet(val id: String, val accountNumber: String, val currency: String, val balance: BigDecimal)

/** One of the user's businesses with its cashbook; the cashbook is null if it couldn't be loaded. */
data class BusinessBalance(val business: Business, val cashbook: BusinessWallet?)

/**
 * Someone a business pays. They join only by accepting an invitation, or by asking with the business's join
 * code and being approved; their FluxPay login is their own.
 */
data class Worker(
    val id: String,
    val name: String,
    /** Empty until they join. */
    val accountNumber: String,
    val currency: String,
    val employeeNumber: String,
    val jobTitle: String,
    /** Null only on a join request that hasn't been approved yet. */
    val salary: BigDecimal?,
    val status: WorkerStatus = WorkerStatus.ACTIVE,
    val statusLabel: String = "",
    /** Why they were suspended, declined or removed. */
    val statusNote: String = "",
    val phoneNumber: String = "",
)

enum class WorkerStatus {
    /** The business invited them; they haven't accepted yet. */
    INVITED,

    /** They asked to join with the business's join code; waiting for an owner or admin. */
    PENDING_ACTIVATION,
    ACTIVE,

    /** On the register, but can't be paid until reactivated. */
    SUSPENDED,
    DEACTIVATED,
    UNKNOWN,
}

/** The business's join code: workers type it, or scan [link] as a QR code, to ask to join. */
data class JoinCode(val enabled: Boolean, val code: String?, val link: String?)

/** A business the user works for (or is invited to, or asked to join), as the worker sees it. */
data class Employer(
    val id: String,
    val business: String,
    val jobTitle: String,
    val status: WorkerStatus,
    val statusLabel: String,
)

/** Who an invitation code is from, shown before the worker accepts it. */
data class InvitationPreview(val business: String, val name: String, val jobTitle: String)

data class WorkerImportResult(val created: Int, val updated: Int, val errors: List<String>)

enum class PayRunStatus { DRAFT, PENDING_APPROVAL, PAID, REJECTED, CANCELLED, UNKNOWN }

data class PayRun(
    val id: String,
    val title: String,
    val payDate: String,
    val status: PayRunStatus,
    val statusLabel: String,
    val currency: String,
    val total: BigDecimal,
    val reversedTotal: BigDecimal,
    val workerCount: Int,
    val reversedCount: Int,
    val createdByName: String,
    val decidedByName: String?,
    val payslips: List<Payslip> = emptyList(),
)

data class Payslip(
    val id: String,
    val workerName: String,
    val accountNumber: String,
    val jobTitle: String,
    val amount: BigDecimal,
    val status: String,
    val statusLabel: String,
    val reference: String?,
    val reversalReason: String,
) {
    val isPaid: Boolean get() = status == "PAID"
    val isReversed: Boolean get() = status == "REVERSED"
}

data class MyPayslip(
    val id: String,
    val business: String,
    val title: String,
    val payDate: String,
    val amount: BigDecimal,
    val currency: String,
    val statusLabel: String,
    val isReversed: Boolean,
    val reversalReason: String,
)

data class BookCategory(val id: Int, val code: String, val name: String, val type: String)

data class BookEntry(
    val id: String,
    val date: String,
    val isMoneyIn: Boolean,
    val amount: BigDecimal,
    val counterparty: String,
    val description: String,
    val sourceLabel: String,
    val category: BookCategory,
    val balance: BigDecimal,
)

data class Cashbook(
    val accountNumber: String,
    val currency: String,
    val opening: BigDecimal,
    val moneyIn: BigDecimal,
    val moneyOut: BigDecimal,
    val closing: BigDecimal,
    val entries: List<BookEntry>,
)

data class SummaryLine(val name: String, val amount: BigDecimal)

data class SummarySection(val title: String, val lines: List<SummaryLine>, val total: BigDecimal)

data class BooksSummary(
    val currency: String,
    val income: SummarySection,
    val expenses: SummarySection,
    val profit: BigDecimal,
    val assets: SummarySection,
    val equity: SummarySection,
    val balanced: Boolean,
)
