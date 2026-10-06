package com.fluxpay.core.domain.model

import java.math.BigDecimal
import java.time.Instant

data class User(
    val id: String,
    val email: String,
    val fullName: String,
    val phoneNumber: String,
)

/** What email + password lead to: signed in, or a code from the authenticator app still needed. */
sealed interface LoginResult {
    data class SignedIn(val user: User) : LoginResult

    /** Two-step verification is on: send a code with [mfaToken] (valid for a few minutes). */
    data class NeedsCode(val mfaToken: String) : LoginResult
}

/** Two-step verification on this account. [required]: they own or run a business (or are FluxPay staff). */
data class MfaStatus(val enabled: Boolean, val required: Boolean, val recoveryCodesLeft: Int)

/** A new authenticator secret: typed in as [secret], or opened in the app as [otpauthUri]. */
data class MfaSetup(val secret: String, val otpauthUri: String)

data class Account(
    val id: String,
    val accountNumber: String,
    val name: String,
    val currency: String,
    val balance: BigDecimal,
    val updatedAt: Instant,
)

enum class TransactionType { CREDIT, DEBIT }

enum class TransactionCategory { TRANSFER_IN, TRANSFER_OUT, BONUS, DEPOSIT, WITHDRAWAL, WITHDRAWAL_REVERSAL, ADJUSTMENT, UNKNOWN }

enum class TransactionStatus { PENDING, COMPLETED, FAILED, UNKNOWN }

data class Transaction(
    val id: String,
    val accountId: String,
    val type: TransactionType,
    val category: TransactionCategory,
    val status: TransactionStatus,
    val amount: BigDecimal,
    val currency: String,
    val balanceAfter: BigDecimal,
    val counterpartyName: String,
    val counterpartyAccount: String,
    val description: String,
    val reference: String,
    val createdAt: Instant,
) {
    val isCredit: Boolean get() = type == TransactionType.CREDIT
}

data class TransactionFilter(
    val accountId: String? = null,
    val type: TransactionType? = null,
    val query: String? = null,
    val from: Instant? = null,
    val to: Instant? = null,
    val limit: Int = 500,
) {
    val isEmpty: Boolean get() = accountId == null && type == null && query.isNullOrBlank() && from == null && to == null
}

/** What we're allowed to show about a recipient before confirming a transfer. */
data class Recipient(
    val accountNumber: String,
    val currency: String,
    val holderName: String,
)

data class TransferReceipt(
    val transferId: String,
    val reference: String,
    val amount: BigDecimal,
    val currency: String,
    val recipientName: String,
    val destinationAccountNumber: String,
    val note: String,
    val createdAt: Instant,
    val transaction: Transaction,
)

enum class ThemeMode { SYSTEM, LIGHT, DARK }

data class UserPreferences(
    /** The currency the dashboard totals in; null until the user picks one (the first wallet's is used). */
    val currency: String? = null,
    val themeMode: ThemeMode = ThemeMode.SYSTEM,
    val hideBalances: Boolean = false,
)

/** Money sent out of FluxPay to M-Pesa: the wallet is debited at once, and M-Pesa confirms it a little later. */
data class MpesaWithdrawal(val id: String, val amount: BigDecimal, val currency: String, val reference: String, val status: String)
