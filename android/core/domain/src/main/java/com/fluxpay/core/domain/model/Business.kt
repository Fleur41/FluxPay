package com.fluxpay.core.domain.model

import java.math.BigDecimal

/** A business the user belongs to, with their role in it (OWNER, ADMIN, FINANCE, VIEWER). */
data class Business(
    val id: String,
    val name: String,
    val role: String,
    val isActive: Boolean,
    /** Payments and pay runs above this need a second owner or admin to approve them. */
    val approvalThreshold: BigDecimal = BigDecimal.ZERO,
) {
    val isOwner: Boolean get() = role == "OWNER"

    /** Owners, admins and finance prepare pay runs and manage workers. */
    val canPrepare: Boolean get() = role in setOf("OWNER", "ADMIN", "FINANCE")

    /** Owners and admins approve pay runs and take back wrong payments. */
    val canApprove: Boolean get() = role in setOf("OWNER", "ADMIN")

    val roleLabel: String get() = role.lowercase().replaceFirstChar { it.uppercase() }

    /** Roles this member may invite, change or remove (the server enforces the same rule). */
    val manageableRoles: List<TeamRole>
        get() = when (role) {
            "OWNER" -> TeamRole.entries
            "ADMIN" -> listOf(TeamRole.FINANCE, TeamRole.VIEWER)
            else -> emptyList()
        }
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
    val approvalThreshold: BigDecimal = BigDecimal.ZERO,
    val walletBalance: BigDecimal = BigDecimal.ZERO,
    /** Owners and admins other than the preparer: who could approve it. */
    val otherApprovers: List<String> = emptyList(),
) {
    val needsApproval: Boolean get() = total > approvalThreshold
    val shortfall: BigDecimal get() = (total - walletBalance).max(BigDecimal.ZERO)
}

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
    /** What the business owes, e.g. unpaid bills (Accounts payable). */
    val liabilities: SummarySection,
    val equity: SummarySection,
    val balanced: Boolean,
)

/** Roles in a business's team, in order of power. Workers aren't members: they are only paid. */
enum class TeamRole(val label: String, val description: String) {
    OWNER("Owner", "Everything, including the approval limit and taking money out"),
    ADMIN("Admin", "Approves payments and pay runs, manages finance and viewers"),
    FINANCE("Finance", "Prepares payments and pay runs, manages workers; can't approve"),
    VIEWER("Viewer", "Sees the wallet, payments and books; changes nothing");

    companion object {
        fun of(role: String) = entries.firstOrNull { it.name == role }
    }
}

/** Someone in the business's team. */
data class Member(val id: String, val email: String, val fullName: String, val role: String) {
    val roleLabel: String get() = TeamRole.of(role)?.label ?: role
}

/** An emailed invitation to join the team that hasn't been accepted yet. */
data class TeamInvitation(val id: String, val email: String, val role: String, val invitedBy: String, val expiresAt: String) {
    val roleLabel: String get() = TeamRole.of(role)?.label ?: role
}

/** A bill the business has to pay (payable), or an invoice it is waiting to be paid (receivable). */
data class Invoice(
    val id: String,
    val isBill: Boolean,
    val number: String,
    val party: String,
    val description: String,
    val category: BookCategory,
    val amount: BigDecimal,
    val paid: BigDecimal,
    val outstanding: BigDecimal,
    val issueDate: String,
    val dueDate: String?,
    val isOverdue: Boolean,
    val status: String,
    val statusLabel: String,
    /** The cashbook entries that paid it: date, amount, counterparty. */
    val payments: List<Triple<String, BigDecimal, String>>,
) {
    val isOpen: Boolean get() = status == "OPEN" || status == "PART_PAID"
}

data class InvoiceTotals(
    val payable: BigDecimal,
    val receivable: BigDecimal,
    val payableOverdue: BigDecimal,
    val receivableOverdue: BigDecimal,
)

data class Invoices(val currency: String, val totals: InvoiceTotals, val items: List<Invoice>)

/** Ways a supplier can be paid, and the details each needs. */
enum class PayoutMethod(val label: String, val fields: List<Pair<String, String>>) {
    MPESA_MOBILE("M-Pesa number", listOf("mpesa_phone" to "M-Pesa phone number")),
    MPESA_PAYBILL("M-Pesa paybill", listOf("paybill_number" to "Paybill number", "paybill_account" to "Account number")),
    MPESA_TILL("M-Pesa till (Buy Goods)", listOf("till_number" to "Till number")),
    FLUXPAY("FluxPay account", listOf("account_number" to "FluxPay account number")),
    BANK("Bank transfer", listOf("bank_name" to "Bank", "bank_branch" to "Branch", "bank_account_name" to "Account name",
        "bank_account_number" to "Account number")),
}

/** Someone the business pays that isn't a worker: a supplier, contractor, the landlord, a utility. */
data class Supplier(
    val id: String,
    val name: String,
    val kindLabel: String,
    val methodLabel: String,
    /** The payout details in one line, masked for viewers. */
    val details: String,
    /** Payments only go out once an owner or admin has checked the payout details. */
    val isVerified: Boolean,
    val verifiedBy: String?,
    val detailsChangedBy: String?,
)

/** A payment out of the business cashbook to a supplier (or anyone else), outside payroll. */
data class BusinessPayment(
    val id: String,
    val reference: String,
    val recipient: String,
    val typeLabel: String,
    val amount: BigDecimal,
    val currency: String,
    val status: String,
    val statusLabel: String,
    val note: String,
    val createdBy: String,
    val decidedBy: String?,
    val failureReason: String?,
    val date: String,
    val payoutMethod: String?,
) {
    val waitingForApproval: Boolean get() = status == "PENDING_APPROVAL"
}
