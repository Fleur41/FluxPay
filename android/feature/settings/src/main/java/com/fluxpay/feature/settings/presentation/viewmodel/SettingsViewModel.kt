package com.fluxpay.feature.settings.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.config.AppConfig
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.usecase.LogoutUseCase
import com.fluxpay.core.domain.usecase.ObservePreferencesUseCase
import com.fluxpay.core.domain.usecase.ObserveProfileUseCase
import com.fluxpay.feature.settings.domain.usecase.UpdatePreferencesUseCase
import com.fluxpay.feature.settings.presentation.state.SettingsUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@HiltViewModel
class SettingsViewModel @Inject constructor(
    observeProfile: ObserveProfileUseCase,
    observePreferences: ObservePreferencesUseCase,
    private val updatePreferences: UpdatePreferencesUseCase,
    private val logoutUseCase: LogoutUseCase,
    appConfig: AppConfig,
) : ViewModel() {

    private val loggingOut = MutableStateFlow(false)

    val state: StateFlow<SettingsUiState> = combine(observeProfile(), observePreferences(), loggingOut) { user, prefs, out ->
        SettingsUiState(
            user = user,
            preferences = prefs,
            appVersion = appConfig.versionName,
            environment = appConfig.environment,
            isLoggingOut = out,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SettingsUiState())

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
