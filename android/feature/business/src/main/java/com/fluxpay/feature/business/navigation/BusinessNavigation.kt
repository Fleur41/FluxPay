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
import com.fluxpay.feature.business.presentation.JoinTeamScreen
import com.fluxpay.feature.business.presentation.NewBusinessScreen
import com.fluxpay.feature.business.presentation.PayRunDetailScreen
import com.fluxpay.feature.business.presentation.PayRunsScreen
import com.fluxpay.feature.business.presentation.SuppliersScreen
import com.fluxpay.feature.business.presentation.TeamScreen
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
    const val TEAM = "business/{$BUSINESS_ID}/team"
    const val SUPPLIERS = "business/{$BUSINESS_ID}/suppliers"

    // Anyone, from Settings (the Business tab only shows once they're in a business).
    const val NEW = "new-business"
    const val TOKEN = "token"
    const val JOIN_TEAM = "join-business?$TOKEN={$TOKEN}"
    const val JOIN_TEAM_START = "join-business"

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
        BusinessHubScreen(
            onOpenBusiness = { id -> navController.navigate("business/$id") },
            onNewBusiness = { navController.navigate(BusinessRoutes.NEW) },
        )
    }
    composable(BusinessRoutes.HOME, arguments = listOf(businessArg)) {
        BusinessHomeScreen(
            onBack = navController::popBackStack,
            onWorkers = { id, tab -> navController.navigate("business/$id/workers" + (tab?.let { "?tab=$it" } ?: "")) },
            onPayRuns = { id -> navController.navigate("business/$id/pay-runs") },
            onBooks = { id -> navController.navigate("business/$id/books") },
            onTeam = { id -> navController.navigate("business/$id/team") },
            onSuppliers = { id -> navController.navigate("business/$id/suppliers") },
            onSecurity = { navController.navigate("settings/security") },
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
    composable(BusinessRoutes.SUPPLIERS, arguments = listOf(businessArg)) {
        SuppliersScreen(onBack = navController::popBackStack)
    }
    composable(BusinessRoutes.TEAM, arguments = listOf(businessArg)) {
        TeamScreen(
            onBack = navController::popBackStack,
            // They left: the business is gone for them, so back past its pages.
            onLeft = { navController.popBackStack(BusinessRoutes.HOME, inclusive = true) },
        )
    }
    composable(BusinessRoutes.NEW) {
        NewBusinessScreen(onBack = navController::popBackStack, onCreated = { id -> navController.openBusiness(id, BusinessRoutes.NEW) })
    }
    composable(
        BusinessRoutes.JOIN_TEAM,
        arguments = listOf(optional(BusinessRoutes.TOKEN)),
        // From the team invitation email.
        deepLinks = listOf(navDeepLink { uriPattern = "fluxpay://join-business?token={${BusinessRoutes.TOKEN}}" }),
    ) {
        JoinTeamScreen(
            onBack = navController::popBackStack,
            onJoined = { id -> navController.openBusiness(id, BusinessRoutes.JOIN_TEAM) },
        )
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

/** Opens a business the user just started or joined, in place of the screen that got them there. */
private fun NavController.openBusiness(id: String, from: String) =
    navigate("business/$id") { popUpTo(from) { inclusive = true } }
