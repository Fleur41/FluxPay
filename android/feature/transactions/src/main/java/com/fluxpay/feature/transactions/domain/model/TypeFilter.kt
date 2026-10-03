package com.fluxpay.feature.transactions.domain.model

import com.fluxpay.core.domain.model.TransactionType

enum class TypeFilter(val label: String, val type: TransactionType?) {
    ALL("All", null),
    MONEY_IN("Money in", TransactionType.CREDIT),
    MONEY_OUT("Money out", TransactionType.DEBIT),
}
