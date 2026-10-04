package com.fluxpay.feature.settings.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.config.AppConfig
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.NotificationSettings
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.usecase.LogoutUseCase
import com.fluxpay.core.domain.usecase.ObservePlatformConfigUseCase
import com.fluxpay.core.domain.usecase.ObservePreferencesUseCase
import com.fluxpay.core.domain.usecase.ObserveProfileUseCase
import com.fluxpay.feature.settings.domain.usecase.NotificationSettingsUseCase
import com.fluxpay.feature.settings.domain.usecase.UpdatePreferencesUseCase
import com.fluxpay.feature.settings.presentation.state.AlertsState
import com.fluxpay.feature.settings.presentation.state.SettingsUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@HiltViewModel
class SettingsViewModel @Inject constructor(
    observeProfile: ObserveProfileUseCase,
    observePreferences: ObservePreferencesUseCase,
    observeConfig: ObservePlatformConfigUseCase,
    private val updatePreferences: UpdatePreferencesUseCase,
    private val notificationSettings: NotificationSettingsUseCase,
    private val logoutUseCase: LogoutUseCase,
    appConfig: AppConfig,
) : ViewModel() {

    private val loggingOut = MutableStateFlow(false)
    private val alerts = MutableStateFlow(AlertsState())

    val state: StateFlow<SettingsUiState> = combine(
        observeProfile(),
        observePreferences(),
        loggingOut,
        alerts,
        observeConfig(),
    ) { user, prefs, out, alertsState, config ->
        SettingsUiState(
            user = user,
            preferences = prefs,
            appVersion = appConfig.versionName,
            environment = appConfig.environment,
            isLoggingOut = out,
            alerts = alertsState,
            currencies = config?.currencies.orEmpty().map { it.code },
            selectedCurrency = prefs.currency ?: config?.defaultCurrency,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SettingsUiState())

    init {
        loadAlerts()
    }

    fun loadAlerts() {
        viewModelScope.launch {
            when (val result = notificationSettings.load()) {
                is NetworkResult.Success -> alerts.value = AlertsState(result.data.emailEnabled, result.data.smsEnabled)
                is NetworkResult.Error -> alerts.update { it.copy(error = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun setEmailAlerts(enabled: Boolean) = changeAlert(
        apply = { it.copy(emailEnabled = enabled) },
        revert = { it.copy(emailEnabled = !enabled) },
    ) { notificationSettings.setEmail(enabled) }

    fun setSmsAlerts(enabled: Boolean) = changeAlert(
        apply = { it.copy(smsEnabled = enabled) },
        revert = { it.copy(smsEnabled = !enabled) },
    ) { notificationSettings.setSms(enabled) }

    /** Flips the switch at once; flips it back with the server's message if saving fails. */
    private fun changeAlert(
        apply: (AlertsState) -> AlertsState,
        revert: (AlertsState) -> AlertsState,
        save: suspend () -> NetworkResult<NotificationSettings>,
    ) {
        alerts.update { apply(it).copy(error = null) }
        viewModelScope.launch {
            val result = save()
            if (result is NetworkResult.Error) alerts.update { revert(it).copy(error = result.message) }
        }
    }

    fun setCurrency(code: String) {
        viewModelScope.launch { updatePreferences.currency(code) }
    }

    fun setTheme(mode: ThemeMode) {
        viewModelScope.launch { updatePreferences.theme(mode) }
    }

    fun setHideBalances(hide: Boolean) {
        viewModelScope.launch { updatePreferences.hideBalances(hide) }
    }

    /** The app's root observes the session and returns to login once tokens are cleared. */
    fun logout() {
        if (loggingOut.value) return
        loggingOut.value = true
        viewModelScope.launch { logoutUseCase(revokeRemotely = true) }
    }
}
