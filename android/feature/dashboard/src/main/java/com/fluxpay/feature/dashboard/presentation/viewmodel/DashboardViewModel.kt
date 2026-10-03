package com.fluxpay.feature.dashboard.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.feature.dashboard.presentation.state.DashboardUiState
import com.fluxpay.feature.dashboard.domain.usecase.ObserveDashboardUseCase
import com.fluxpay.feature.dashboard.domain.usecase.RefreshDashboardUseCase
import com.fluxpay.feature.dashboard.domain.usecase.SetHideBalancesUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@HiltViewModel
class DashboardViewModel @Inject constructor(
    observeDashboard: ObserveDashboardUseCase,
    private val refreshDashboard: RefreshDashboardUseCase,
    private val setHideBalances: SetHideBalancesUseCase,
) : ViewModel() {

    private val refreshing = MutableStateFlow(false)
    private val error = MutableStateFlow<NetworkResult.Error?>(null)
    private var refreshJob: Job? = null

    val state: StateFlow<DashboardUiState> = combine(observeDashboard(), refreshing, error) { summary, isRefreshing, err ->
        DashboardUiState(summary = summary, isRefreshing = isRefreshing, error = err)
    }.stateIn(
        scope = viewModelScope,
        // Keeps the upstream alive for 5s across configuration changes, then stops collecting.
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = DashboardUiState(isRefreshing = true),
    )

    init {
        refresh()
    }

    fun refresh() {
        if (refreshJob?.isActive == true) return
        refreshJob = viewModelScope.launch {
            refreshing.value = true
            error.value = refreshDashboard() as? NetworkResult.Error
            refreshing.value = false
        }
    }

    fun toggleHideBalances() {
        val hidden = state.value.summary?.hideBalances ?: false
        viewModelScope.launch { setHideBalances(!hidden) }
    }

    fun dismissError() {
        error.value = null
    }
}
