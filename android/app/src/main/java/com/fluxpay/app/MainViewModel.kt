package com.fluxpay.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.usecase.LogoutUseCase
import com.fluxpay.core.domain.usecase.ObserveCanSeeBusinessUseCase
import com.fluxpay.core.domain.usecase.ObservePreferencesUseCase
import com.fluxpay.core.domain.usecase.ObserveSessionUseCase
import com.fluxpay.core.domain.usecase.RefreshMyBusinessesUseCase
import com.fluxpay.core.domain.usecase.RefreshPlatformConfigUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed interface MainUiState {
    data object Loading : MainUiState
    data class Ready(val isLoggedIn: Boolean, val themeMode: ThemeMode) : MainUiState
}

@HiltViewModel
class MainViewModel @Inject constructor(
    observeSession: ObserveSessionUseCase,
    observePreferences: ObservePreferencesUseCase,
    private val logoutUseCase: LogoutUseCase,
    private val refreshConfig: RefreshPlatformConfigUseCase,
    observeCanSeeBusiness: ObserveCanSeeBusinessUseCase,
    private val refreshMyBusinesses: RefreshMyBusinessesUseCase,
) : ViewModel() {

    /** The splash screen stays up until this leaves Loading. */
    val uiState: StateFlow<MainUiState> = combine(observeSession(), observePreferences()) { loggedIn, prefs ->
        MainUiState.Ready(isLoggedIn = loggedIn, themeMode = prefs.themeMode)
    }.stateIn(viewModelScope, SharingStarted.Eagerly, MainUiState.Loading)

    /** The Business tab is for people who run a business; workers and personal users don't see it. */
    val showBusinessTab: StateFlow<Boolean> =
        observeCanSeeBusiness().stateIn(viewModelScope, SharingStarted.Eagerly, false)

    /**
     * Deep links are parked here (as plain strings — no Context or Intent is held) until
     * the UI can act on them, e.g. a transaction link opened while signed out waits for login.
     */
    private val _pendingDeepLink = MutableStateFlow<String?>(null)
    val pendingDeepLink: StateFlow<String?> = _pendingDeepLink.asStateFlow()

    init {
        // If the session ends for any reason other than tapping "Sign out" (refresh token
        // expired, inactivity timeout…), still wipe the cached financial data.
        var wasLoggedIn = false
        observeSession()
            .onEach { loggedIn ->
                if (wasLoggedIn && !loggedIn) viewModelScope.launch { logoutUseCase(revokeRemotely = false) }
                // Business rules (limits, currencies, timeout) are re-read at each sign-in, so staff changes
                // reach phones without an app update. A failure keeps the cached copy.
                if (loggedIn && !wasLoggedIn) {
                    viewModelScope.launch { refreshConfig() }
                    viewModelScope.launch { refreshMyBusinesses() } // decides whether the Business tab shows
                }
                wasLoggedIn = loggedIn
            }
            .launchIn(viewModelScope)
        viewModelScope.launch { refreshConfig() } // at start-up too: the sign-up screen needs currencies
    }

    fun onDeepLink(link: String) {
        _pendingDeepLink.value = link
    }

    fun onDeepLinkConsumed() {
        _pendingDeepLink.value = null
    }
}
