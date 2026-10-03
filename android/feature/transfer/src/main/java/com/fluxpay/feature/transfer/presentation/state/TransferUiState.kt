package com.fluxpay.feature.transfer.presentation.state

import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.Recipient
import com.fluxpay.core.domain.model.TransferReceipt
import com.fluxpay.feature.transfer.domain.model.TransferFormErrors
import java.math.BigDecimal

sealed interface TransferStep {
    data object Form : TransferStep

    data class Review(
        val source: Account,
        val recipient: Recipient,
        val amount: BigDecimal,
        val note: String,
        /** Generated once per review and reused for retries, so a retry can't double-send. */
        val idempotencyKey: String,
    ) : TransferStep

    data class Success(val receipt: TransferReceipt) : TransferStep
}

data class TransferUiState(
    val accounts: List<Account> = emptyList(),
    val selectedAccountId: String? = null,
    val recipientNumber: String = "",
    val amountText: String = "",
    val note: String = "",
    val errors: TransferFormErrors = TransferFormErrors(),
    val step: TransferStep = TransferStep.Form,
    val isWorking: Boolean = false,
    val errorMessage: String? = null,
    val hideBalances: Boolean = false,
) {
    val selectedAccount: Account? get() = accounts.firstOrNull { it.id == selectedAccountId } ?: accounts.firstOrNull()
}
