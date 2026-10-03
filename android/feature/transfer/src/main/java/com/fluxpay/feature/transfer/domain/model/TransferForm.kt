package com.fluxpay.feature.transfer.domain.model

import java.math.BigDecimal

data class TransferFormErrors(
    val source: String? = null,
    val recipient: String? = null,
    val amount: String? = null,
    val note: String? = null,
) {
    val isValid: Boolean get() = source == null && recipient == null && amount == null && note == null
}

data class TransferValidation(
    val errors: TransferFormErrors,
    /** Parsed amount, present only when the form is valid. */
    val amount: BigDecimal?,
)
