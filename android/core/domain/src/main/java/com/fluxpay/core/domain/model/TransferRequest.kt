package com.fluxpay.core.domain.model

import java.math.BigDecimal
import java.util.UUID

/**
 * Immutable transfer command, created through [Builder] (Builder pattern) so every
 * instance that exists is already valid.
 */
class TransferRequest private constructor(
    val sourceAccountId: String,
    val destinationAccountNumber: String,
    val amount: BigDecimal,
    val note: String,
    /** Re-sent unchanged on retries so the backend never sends money twice. */
    val idempotencyKey: String,
) {
    class Builder {
        private var sourceAccountId: String? = null
        private var destinationAccountNumber: String? = null
        private var amount: BigDecimal? = null
        private var note: String = ""
        private var idempotencyKey: String? = null

        fun from(accountId: String) = apply { sourceAccountId = accountId }
        fun to(accountNumber: String) = apply { destinationAccountNumber = accountNumber.trim() }
        fun amount(value: BigDecimal) = apply { amount = value }
        fun note(value: String) = apply { note = value.trim() }
        fun idempotencyKey(value: String) = apply { idempotencyKey = value }

        fun build(): TransferRequest {
            val source = requireNotNull(sourceAccountId) { "Source account is required" }
            val destination = requireNotNull(destinationAccountNumber) { "Recipient account is required" }
            val value = requireNotNull(amount) { "Amount is required" }
            require(destination.length == 10 && destination.all(Char::isDigit)) { "Account numbers are 10 digits" }
            require(value > BigDecimal.ZERO) { "Amount must be greater than zero" }
            require(value.scale() <= 2) { "Amount can have at most 2 decimal places" }
            require(note.length <= MAX_NOTE_LENGTH) { "Note is too long" }
            return TransferRequest(
                sourceAccountId = source,
                destinationAccountNumber = destination,
                amount = value,
                note = note,
                idempotencyKey = idempotencyKey ?: UUID.randomUUID().toString(),
            )
        }
    }

    companion object {
        const val MAX_NOTE_LENGTH = 140
        fun builder() = Builder()
    }
}
