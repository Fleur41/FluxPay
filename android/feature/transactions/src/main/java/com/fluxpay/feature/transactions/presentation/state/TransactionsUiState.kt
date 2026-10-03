package com.fluxpay.feature.transactions.presentation.state

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.ui.adapter.TransactionListItem
import com.fluxpay.feature.transactions.domain.model.TypeFilter

data class TransactionsUiState(
    val items: List<TransactionListItem> = emptyList(),
    val query: String = "",
    val typeFilter: TypeFilter = TypeFilter.ALL,
    val hideAmounts: Boolean = false,
    val isRefreshing: Boolean = false,
    val isLoaded: Boolean = false,
    val error: NetworkResult.Error? = null,
) {
    val isFiltering: Boolean get() = query.isNotBlank() || typeFilter != TypeFilter.ALL
}

data class TransactionDetailUiState(
    val transaction: Transaction? = null,
    val hideAmounts: Boolean = false,
    val isLoading: Boolean = true,
    val error: NetworkResult.Error? = null,
)
