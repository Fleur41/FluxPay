package com.fluxpay.feature.transactions.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.usecase.ObservePreferencesUseCase
import com.fluxpay.core.ui.adapter.TransactionListAdapter
import com.fluxpay.feature.transactions.domain.model.TypeFilter
import com.fluxpay.feature.transactions.domain.usecase.ObserveFilteredTransactionsUseCase
import com.fluxpay.feature.transactions.domain.usecase.RefreshTransactionsUseCase
import com.fluxpay.feature.transactions.presentation.state.TransactionsUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@OptIn(ExperimentalCoroutinesApi::class, FlowPreview::class)
@HiltViewModel
class TransactionsViewModel @Inject constructor(
    observeTransactions: ObserveFilteredTransactionsUseCase,
    observePreferences: ObservePreferencesUseCase,
    private val refreshTransactions: RefreshTransactionsUseCase,
    @Dispatcher(FluxDispatcher.Default) defaultDispatcher: CoroutineDispatcher,
) : ViewModel() {

    private val query = MutableStateFlow("")
    private val typeFilter = MutableStateFlow(TypeFilter.ALL)
    private val refreshing = MutableStateFlow(false)
    private val error = MutableStateFlow<NetworkResult.Error?>(null)
    private var refreshJob: Job? = null

    // Debounce typing; flatMapLatest cancels the previous Room query when the filter changes.
    private val listItems = combine(query.debounce(250), typeFilter, ::Pair)
        .flatMapLatest { (q, type) -> observeTransactions(q, type) }
        .map { TransactionListAdapter.adapt(it) } // grouping off the main thread
        .flowOn(defaultDispatcher)

    val state: StateFlow<TransactionsUiState> = combine(
        listItems,
        query,
        typeFilter,
        observePreferences(),
        combine(refreshing, error, ::Pair),
    ) { items, q, type, prefs, (isRefreshing, err) ->
        TransactionsUiState(
            items = items,
            query = q,
            typeFilter = type,
            hideAmounts = prefs.hideBalances,
            isRefreshing = isRefreshing,
            isLoaded = true,
            error = err,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), TransactionsUiState())

    init {
        refresh()
    }

    fun onQueryChange(value: String) {
        query.value = value
    }

    fun onTypeFilterChange(filter: TypeFilter) {
        typeFilter.value = filter
    }

    fun refresh() {
        if (refreshJob?.isActive == true) return
        refreshJob = viewModelScope.launch {
            refreshing.value = true
            error.value = refreshTransactions() as? NetworkResult.Error
            refreshing.value = false
        }
    }
}
