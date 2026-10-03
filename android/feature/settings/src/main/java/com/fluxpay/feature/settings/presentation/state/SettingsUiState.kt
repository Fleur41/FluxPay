package com.fluxpay.feature.settings.presentation.state

import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.model.UserPreferences

data class SettingsUiState(
    val user: User? = null,
    val preferences: UserPreferences = UserPreferences(),
    val appVersion: String = "",
    val environment: String = "",
    val isLoggingOut: Boolean = false,
)
