package com.fluxpay.feature.settings.presentation.state

import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.model.UserPreferences

data class SettingsUiState(
    val user: User? = null,
    val preferences: UserPreferences = UserPreferences(),
    val appVersion: String = "",
    val environment: String = "",
    val isLoggingOut: Boolean = false,
    val alerts: AlertsState = AlertsState(),
    /** Enabled currencies from the server's platform settings. */
    val currencies: List<String> = emptyList(),
    /** The preferred currency, or the platform default until the user picks one. */
    val selectedCurrency: String? = null,
)

/** Email/SMS transaction alerts. Null switches mean "not loaded yet". */
data class AlertsState(
    val emailEnabled: Boolean? = null,
    val smsEnabled: Boolean? = null,
    val error: String? = null,
)
