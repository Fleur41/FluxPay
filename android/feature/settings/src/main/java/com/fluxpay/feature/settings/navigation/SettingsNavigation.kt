package com.fluxpay.feature.settings.navigation

import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.fluxpay.feature.settings.presentation.SettingsScreen

object SettingsRoutes {
    const val SETTINGS = "settings"
}

fun NavGraphBuilder.settingsScreen(onOpenEmployers: () -> Unit) {
    composable(SettingsRoutes.SETTINGS) { SettingsScreen(onOpenEmployers = onOpenEmployers) }
}
