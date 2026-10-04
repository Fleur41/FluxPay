package com.fluxpay.core.domain.model

import java.io.File
import java.math.BigDecimal
import java.time.LocalDate

/** Which channels transaction alerts go to (stored on the server, per user). */
data class NotificationSettings(
    val emailEnabled: Boolean,
    val smsEnabled: Boolean,
)

enum class StatementFormat(val extension: String, val mimeType: String) {
    PDF("pdf", "application/pdf"),
    CSV("csv", "text/csv"),
}

/** Whole days, both ends included, in the server's display time zone (Africa/Nairobi). */
data class StatementPeriod(val from: LocalDate, val to: LocalDate)

/** A statement saved in the app's private cache, ready to open or share. Deleted on sign-out. */
data class DownloadedStatement(
    val file: File,
    val fileName: String,
    val format: StatementFormat,
)

enum class BudgetKind(val label: String) {
    INCOME("Income"),
    NEEDS("Needs"),
    WANTS("Wants"),
    SAVINGS("Savings"),
}

/** One line of the user's monthly budget, kept only on this phone. */
data class BudgetLine(
    val id: Long = 0,
    val label: String,
    val amount: BigDecimal,
    val kind: BudgetKind,
)
