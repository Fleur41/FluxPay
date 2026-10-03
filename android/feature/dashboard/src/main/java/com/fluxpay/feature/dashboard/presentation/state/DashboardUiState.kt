package com.fluxpay.feature.dashboard.presentation.state

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.feature.dashboard.domain.model.DashboardSummary

data class DashboardUiState(
    val summary: DashboardSummary? = null,
    val isRefreshing: Boolean = false,
    val error: NetworkResult.Error? = null,
)
