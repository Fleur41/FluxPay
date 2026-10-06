package com.fluxpay.feature.settings.navigation

import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.fluxpay.feature.settings.presentation.SecurityScreen
import com.fluxpay.feature.settings.presentation.SettingsScreen

object SettingsRoutes {
    const val SETTINGS = "settings"
    const val SECURITY = "settings/security"
}

fun NavGraphBuilder.settingsScreen(
    navController: NavController,
    onOpenEmployers: () -> Unit,
    onStartBusiness: () -> Unit,
    onJoinTeam: () -> Unit,
) {
    composable(SettingsRoutes.SETTINGS) {
        SettingsScreen(
            onOpenEmployers = onOpenEmployers,
            onStartBusiness = onStartBusiness,
            onJoinTeam = onJoinTeam,
            onOpenSecurity = { navController.navigate(SettingsRoutes.SECURITY) },
        )
    }
    composable(SettingsRoutes.SECURITY) { SecurityScreen(onBack = navController::popBackStack) }
}
