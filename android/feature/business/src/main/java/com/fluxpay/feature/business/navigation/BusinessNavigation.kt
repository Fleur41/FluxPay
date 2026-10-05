package com.fluxpay.feature.business.navigation

import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import androidx.navigation.navDeepLink
import com.fluxpay.feature.business.presentation.BooksScreen
import com.fluxpay.feature.business.presentation.BusinessHomeScreen
import com.fluxpay.feature.business.presentation.BusinessHubScreen
import com.fluxpay.feature.business.presentation.EmployersScreen
import com.fluxpay.feature.business.presentation.JoinBusinessScreen
import com.fluxpay.feature.business.presentation.PayRunDetailScreen
import com.fluxpay.feature.business.presentation.PayRunsScreen
import com.fluxpay.feature.business.presentation.WorkersScreen

object BusinessRoutes {
    const val HUB = "business"
    const val BUSINESS_ID = "businessId"
    const val RUN_ID = "runId"
    const val TAB = "tab"
    const val CODE = "code"
    const val JOIN_CODE = "business"
    const val HOME = "business/{$BUSINESS_ID}"
    const val WORKERS = "business/{$BUSINESS_ID}/workers?$TAB={$TAB}"
    const val PAY_RUNS = "business/{$BUSINESS_ID}/pay-runs"
    const val PAY_RUN = "business/{$BUSINESS_ID}/pay-runs/{$RUN_ID}"
    const val BOOKS = "business/{$BUSINESS_ID}/books"

    // As a worker (reachable from Home and Settings; workers don't have the Business tab).
    const val EMPLOYERS = "employers"
    const val JOIN = "employers/join?$CODE={$CODE}&$JOIN_CODE={$JOIN_CODE}"
    const val JOIN_START = "employers/join"
}

private fun optional(name: String) = navArgument(name) { type = NavType.StringType; nullable = true; defaultValue = null }

private val businessArg = navArgument(BusinessRoutes.BUSINESS_ID) { type = NavType.StringType }

/**
 * The Business tab (the user's businesses: payroll and books), and the worker's side: the businesses they work
 * for, and joining one with an invitation or a join code.
 */
fun NavGraphBuilder.businessScreens(navController: NavController) {
    composable(BusinessRoutes.HUB) {
        BusinessHubScreen(onOpenBusiness = { id -> navController.navigate("business/$id") })
    }
    composable(BusinessRoutes.HOME, arguments = listOf(businessArg)) {
        BusinessHomeScreen(
            onBack = navController::popBackStack,
            onWorkers = { id, tab -> navController.navigate("business/$id/workers" + (tab?.let { "?tab=$it" } ?: "")) },
            onPayRuns = { id -> navController.navigate("business/$id/pay-runs") },
            onBooks = { id -> navController.navigate("business/$id/books") },
        )
    }
    composable(BusinessRoutes.WORKERS, arguments = listOf(businessArg, optional(BusinessRoutes.TAB))) {
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
    composable(BusinessRoutes.EMPLOYERS) {
        EmployersScreen(onBack = navController::popBackStack, onJoin = { navController.navigate(BusinessRoutes.JOIN_START) })
    }
    composable(
        BusinessRoutes.JOIN,
        arguments = listOf(optional(BusinessRoutes.CODE), optional(BusinessRoutes.JOIN_CODE)),
        // From the invitation SMS/email, or a business's QR code scanned with the phone's camera app.
        deepLinks = listOf(
            navDeepLink { uriPattern = "fluxpay://join-employer?code={${BusinessRoutes.CODE}}" },
            navDeepLink { uriPattern = "fluxpay://join-employer?business={${BusinessRoutes.JOIN_CODE}}" },
        ),
    ) {
        JoinBusinessScreen(
            onBack = navController::popBackStack,
            onDone = {
                navController.navigate(BusinessRoutes.EMPLOYERS) { popUpTo(BusinessRoutes.JOIN) { inclusive = true } }
            },
        )
    }
}
