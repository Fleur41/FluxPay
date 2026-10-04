package com.fluxpay.feature.business.navigation

import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.fluxpay.feature.business.presentation.BooksScreen
import com.fluxpay.feature.business.presentation.BusinessHomeScreen
import com.fluxpay.feature.business.presentation.BusinessHubScreen
import com.fluxpay.feature.business.presentation.PayRunDetailScreen
import com.fluxpay.feature.business.presentation.PayRunsScreen
import com.fluxpay.feature.business.presentation.WorkersScreen

object BusinessRoutes {
    const val HUB = "business"
    const val BUSINESS_ID = "businessId"
    const val RUN_ID = "runId"
    const val HOME = "business/{$BUSINESS_ID}"
    const val WORKERS = "business/{$BUSINESS_ID}/workers"
    const val PAY_RUNS = "business/{$BUSINESS_ID}/pay-runs"
    const val PAY_RUN = "business/{$BUSINESS_ID}/pay-runs/{$RUN_ID}"
    const val BOOKS = "business/{$BUSINESS_ID}/books"
}

private val businessArg = navArgument(BusinessRoutes.BUSINESS_ID) { type = NavType.StringType }

/** The Business tab: the user's businesses (payroll and books) and their own payslips as a worker. */
fun NavGraphBuilder.businessScreens(navController: NavController) {
    composable(BusinessRoutes.HUB) {
        BusinessHubScreen(onOpenBusiness = { id -> navController.navigate("business/$id") })
    }
    composable(BusinessRoutes.HOME, arguments = listOf(businessArg)) {
        BusinessHomeScreen(
            onBack = navController::popBackStack,
            onWorkers = { id -> navController.navigate("business/$id/workers") },
            onPayRuns = { id -> navController.navigate("business/$id/pay-runs") },
            onBooks = { id -> navController.navigate("business/$id/books") },
        )
    }
    composable(BusinessRoutes.WORKERS, arguments = listOf(businessArg)) {
        WorkersScreen(onBack = navController::popBackStack)
    }
    composable(BusinessRoutes.PAY_RUNS, arguments = listOf(businessArg)) {
        PayRunsScreen(
            onBack = navController::popBackStack,
            onOpenRun = { businessId, runId -> navController.navigate("business/$businessId/pay-runs/$runId") },
        )
    }
    composable(
        BusinessRoutes.PAY_RUN,
        arguments = listOf(businessArg, navArgument(BusinessRoutes.RUN_ID) { type = NavType.StringType }),
    ) {
        PayRunDetailScreen(onBack = navController::popBackStack)
    }
    composable(BusinessRoutes.BOOKS, arguments = listOf(businessArg)) {
        BooksScreen(onBack = navController::popBackStack)
    }
}
