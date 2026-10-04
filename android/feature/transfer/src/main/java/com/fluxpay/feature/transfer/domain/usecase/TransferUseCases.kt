package com.fluxpay.feature.transfer.domain.usecase

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.common.util.isValidAccountNumber
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.CurrencyRule
import com.fluxpay.core.domain.model.Recipient
import com.fluxpay.core.domain.model.TransferReceipt
import com.fluxpay.core.domain.model.TransferRequest
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.domain.repository.TransferRepository
import com.fluxpay.feature.transfer.domain.model.TransferFormErrors
import com.fluxpay.feature.transfer.domain.model.TransferValidation
import javax.inject.Inject

class ValidateTransferUseCase @Inject constructor() {

    /**
     * `rule` holds the source currency's limits from the server's platform settings. When it hasn't
     * loaded yet the limits are left to the server, which always enforces them.
     */
    operator fun invoke(
        source: Account?,
        rule: CurrencyRule?,
        recipient: String,
        amountText: String,
        note: String,
    ): TransferValidation {
        val amount = MoneyFormatter.parse(amountText)
        val errors = TransferFormErrors(
            source = if (source == null) "Choose the wallet to send from" else null,
            recipient = when {
                recipient.isBlank() -> "Enter the recipient's account number"
                !recipient.isValidAccountNumber() -> "Account numbers are 10 digits"
                source != null && recipient == source.accountNumber -> "That's the wallet you're sending from"
                else -> null
            },
            amount = when {
                amountText.isBlank() -> "Enter an amount"
                amount == null -> "Enter a valid amount (max 2 decimals)"
                rule != null && amount < rule.minTransfer ->
                    "The minimum is ${MoneyFormatter.format(rule.minTransfer, rule.code)}"
                rule != null && amount > rule.maxTransfer ->
                    "The most you can send at once is ${MoneyFormatter.format(rule.maxTransfer, rule.code)}"
                amount.signum() <= 0 -> "Enter an amount above zero"
                source != null && amount > source.balance ->
                    "Insufficient funds. Available: ${MoneyFormatter.format(source.balance, source.currency)}"
                else -> null
            },
            note = if (note.length > TransferRequest.MAX_NOTE_LENGTH) "Keep the note under 140 characters" else null,
        )
        return TransferValidation(errors, amount.takeIf { errors.isValid })
    }
}

class LookupRecipientUseCase @Inject constructor(private val accountRepository: AccountRepository) {
    suspend operator fun invoke(accountNumber: String): NetworkResult<Recipient> =
        accountRepository.lookupRecipient(accountNumber)
}

class SendMoneyUseCase @Inject constructor(private val transferRepository: TransferRepository) {
    suspend operator fun invoke(request: TransferRequest): NetworkResult<TransferReceipt> =
        transferRepository.send(request)
}
