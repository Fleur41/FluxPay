package com.fluxpay.feature.auth.navigation

import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import androidx.navigation.navDeepLink
import androidx.navigation.navigation
import com.fluxpay.core.common.util.Constants
import com.fluxpay.feature.auth.presentation.ForgotPasswordScreen
import com.fluxpay.feature.auth.presentation.LoginScreen
import com.fluxpay.feature.auth.presentation.RegisterScreen
import com.fluxpay.feature.auth.presentation.ResetPasswordScreen

object AuthRoutes {
    const val GRAPH = "auth_graph"
    const val LOGIN = "auth/login"
    const val REGISTER = "auth/register"
    const val FORGOT_PASSWORD = "auth/forgot-password"

    const val ARG_UID = "uid"
    const val ARG_TOKEN = "token"
    const val RESET_PASSWORD = "auth/reset-password?$ARG_UID={$ARG_UID}&$ARG_TOKEN={$ARG_TOKEN}"

    /** Links sent by the Django password-reset email. */
    val RESET_DEEP_LINKS = listOf(
        "${Constants.DEEP_LINK_SCHEME}://reset-password?$ARG_UID={$ARG_UID}&$ARG_TOKEN={$ARG_TOKEN}",
        "https://${Constants.DEEP_LINK_HOST}/reset-password?$ARG_UID={$ARG_UID}&$ARG_TOKEN={$ARG_TOKEN}",
    )
}

fun NavGraphBuilder.authGraph(navController: NavController) {
    navigation(startDestination = AuthRoutes.LOGIN, route = AuthRoutes.GRAPH) {
        composable(AuthRoutes.LOGIN) {
            LoginScreen(
                onRegisterClick = { navController.navigate(AuthRoutes.REGISTER) },
                onForgotPasswordClick = { navController.navigate(AuthRoutes.FORGOT_PASSWORD) },
            )
        }
        composable(AuthRoutes.REGISTER) {
            RegisterScreen(onBack = navController::popBackStack)
        }
        composable(AuthRoutes.FORGOT_PASSWORD) {
            ForgotPasswordScreen(onBack = navController::popBackStack)
        }
        composable(
            route = AuthRoutes.RESET_PASSWORD,
            arguments = listOf(
                navArgument(AuthRoutes.ARG_UID) { type = NavType.StringType; nullable = true },
                navArgument(AuthRoutes.ARG_TOKEN) { type = NavType.StringType; nullable = true },
            ),
            deepLinks = AuthRoutes.RESET_DEEP_LINKS.map { pattern -> navDeepLink { uriPattern = pattern } },
        ) {
            ResetPasswordScreen(
                onDone = {
                    navController.navigate(AuthRoutes.LOGIN) {
                        popUpTo(AuthRoutes.GRAPH) { inclusive = false }
                        launchSingleTop = true
                    }
                },
            )
        }
    }
}
