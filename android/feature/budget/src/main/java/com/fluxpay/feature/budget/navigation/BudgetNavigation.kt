package com.fluxpay.feature.budget.navigation

import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.fluxpay.feature.budget.presentation.BudgetScreen

object BudgetRoutes {
    const val BUDGET = "budget"
}

fun NavController.navigateToBudget() = navigate(BudgetRoutes.BUDGET) { launchSingleTop = true }

fun NavGraphBuilder.budgetScreen(onBack: () -> Unit) {
    composable(BudgetRoutes.BUDGET) { BudgetScreen(onBack = onBack) }
}
