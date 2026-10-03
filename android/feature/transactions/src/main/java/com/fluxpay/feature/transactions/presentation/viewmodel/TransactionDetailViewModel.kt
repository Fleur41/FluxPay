package com.fluxpay.feature.transactions.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.usecase.ObservePreferencesUseCase
import com.fluxpay.feature.transactions.domain.usecase.ObserveTransactionUseCase
import com.fluxpay.feature.transactions.domain.usecase.RefreshTransactionUseCase
import com.fluxpay.feature.transactions.presentation.state.TransactionDetailUiState
import dagger.assisted.Assisted
import dagger.assisted.AssistedFactory
import dagger.assisted.AssistedInject
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * Factory pattern: the transaction id is a runtime value (from a tap or a deep link),
 * so Hilt builds this ViewModel through an @AssistedFactory instead of a plain @Inject.
 */
@HiltViewModel(assistedFactory = TransactionDetailViewModel.Factory::class)
class TransactionDetailViewModel @AssistedInject constructor(
    @Assisted private val transactionId: String,
    observeTransaction: ObserveTransactionUseCase,
    observePreferences: ObservePreferencesUseCase,
    private val refreshTransaction: RefreshTransactionUseCase,
) : ViewModel() {

    @AssistedFactory
    interface Factory {
        fun create(transactionId: String): TransactionDetailViewModel
    }

    private val loading = MutableStateFlow(true)
    private val error = MutableStateFlow<NetworkResult.Error?>(null)

    val state: StateFlow<TransactionDetailUiState> = combine(
        observeTransaction(transactionId),
        observePreferences(),
        loading,
        error,
    ) { transaction, prefs, isLoading, err ->
        TransactionDetailUiState(
            transaction = transaction,
            hideAmounts = prefs.hideBalances,
            isLoading = isLoading && transaction == null,
            error = err,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), TransactionDetailUiState())

    init {
        // Opened from a deep link the row may not be cached yet — fetch it either way.
        retry()
    }

    fun retry() {
        viewModelScope.launch {
            loading.value = true
            error.value = refreshTransaction(transactionId) as? NetworkResult.Error
            loading.value = false
        }
    }
}
