package com.fluxpay.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.navigation
import com.fluxpay.feature.auth.navigation.AuthRoutes
import com.fluxpay.feature.auth.navigation.authGraph
import com.fluxpay.feature.budget.navigation.budgetScreen
import com.fluxpay.feature.budget.navigation.navigateToBudget
import com.fluxpay.feature.business.navigation.BusinessRoutes
import com.fluxpay.feature.business.navigation.businessScreens
import com.fluxpay.feature.dashboard.navigation.DashboardRoutes
import com.fluxpay.feature.dashboard.navigation.dashboardScreen
import com.fluxpay.feature.settings.navigation.settingsScreen
import com.fluxpay.feature.transactions.navigation.navigateToTransaction
import com.fluxpay.feature.transactions.navigation.transactionsScreens
import com.fluxpay.feature.transfer.navigation.transferScreen

const val MAIN_GRAPH = "main_graph"

/**
 * Root graph = two nested graphs:
 *   auth_graph  → login, register, forgot/reset password
 *   main_graph  → dashboard, transfer, transactions (+ detail), business (payroll, books), settings, budget planner
 * Each feature module contributes its own destinations through a NavGraphBuilder extension.
 */
@Composable
fun FluxPayNavHost(
    navController: NavHostController,
    startDestination: String,
    modifier: Modifier = Modifier,
) {
    NavHost(
        navController = navController,
        startDestination = startDestination,
        modifier = modifier
    ) {
        authGraph(navController)

        navigation(startDestination = DashboardRoutes.DASHBOARD, route = MAIN_GRAPH) {
            dashboardScreen(
                onSendMoney = { navController.navigateToTopLevel(TopLevelDestination.SEND) },
                onSeeAllTransactions = { navController.navigateToTopLevel(TopLevelDestination.ACTIVITY) },
                onTransactionClick = { navController.navigateToTransaction(it.id) },
                onOpenBudget = { navController.navigateToBudget() },
                onOpenBusiness = { id -> navController.navigate("business/$id") },
                onJoinEmployer = { navController.navigate(BusinessRoutes.JOIN_START) },
            )
            transferScreen(
                onDone = { navController.navigateToTopLevel(TopLevelDestination.HOME) },
                onViewTransaction = { id -> navController.navigateToTransaction(id) },
            )
            transactionsScreens(navController)
            settingsScreen(onOpenEmployers = { navController.navigate(BusinessRoutes.EMPLOYERS) })
            budgetScreen(onBack = navController::popBackStack)
            businessScreens(navController)
        }
    }
}

/** Standard bottom-nav behaviour: one copy of each tab, state saved/restored per tab. */
fun NavHostController.navigateToTopLevel(destination: TopLevelDestination) {
    navigate(destination.route) {
        popUpTo(DashboardRoutes.DASHBOARD) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

fun NavHostController.navigateToMainGraph() {
    navigate(MAIN_GRAPH) {
        popUpTo(AuthRoutes.GRAPH) { inclusive = true }
        launchSingleTop = true
    }
}

fun NavHostController.navigateToAuthGraph() {
    navigate(AuthRoutes.GRAPH) {
        popUpTo(graph.id) { inclusive = true } // clear everything: nothing from the old session stays
        launchSingleTop = true
    }
}
