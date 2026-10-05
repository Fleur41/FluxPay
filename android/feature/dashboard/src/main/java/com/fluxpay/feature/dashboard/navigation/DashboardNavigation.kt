package com.fluxpay.feature.dashboard.navigation

import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.feature.dashboard.presentation.DashboardScreen

object DashboardRoutes {
    const val DASHBOARD = "dashboard"
}

fun NavGraphBuilder.dashboardScreen(
    onSendMoney: () -> Unit,
    onSeeAllTransactions: () -> Unit,
    onTransactionClick: (Transaction) -> Unit,
    onOpenBudget: () -> Unit,
    onOpenBusiness: (String) -> Unit,
    onJoinEmployer: () -> Unit,
) {
    composable(DashboardRoutes.DASHBOARD) {
        DashboardScreen(
            onSendMoney = onSendMoney,
            onSeeAllTransactions = onSeeAllTransactions,
            onTransactionClick = onTransactionClick,
            onOpenBudget = onOpenBudget,
            onOpenBusiness = onOpenBusiness,
            onJoinEmployer = onJoinEmployer,
        )
    }
}
