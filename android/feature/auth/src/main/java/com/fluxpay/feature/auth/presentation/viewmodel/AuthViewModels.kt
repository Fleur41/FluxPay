package com.fluxpay.feature.auth.presentation.viewmodel

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.util.isValidEmail
import com.fluxpay.core.domain.usecase.ObservePlatformConfigUseCase
import com.fluxpay.core.domain.usecase.RefreshPlatformConfigUseCase
import com.fluxpay.feature.auth.domain.model.FieldErrors
import com.fluxpay.feature.auth.domain.usecase.ConfirmPasswordResetUseCase
import com.fluxpay.feature.auth.domain.usecase.LoginUseCase
import com.fluxpay.feature.auth.domain.usecase.RegisterUseCase
import com.fluxpay.feature.auth.domain.usecase.RequestPasswordResetUseCase
import com.fluxpay.feature.auth.domain.usecase.ValidateCredentialsUseCase
import com.fluxpay.feature.auth.navigation.AuthRoutes
import com.fluxpay.feature.auth.presentation.state.ForgotPasswordUiState
import com.fluxpay.feature.auth.presentation.state.LoginUiState
import com.fluxpay.feature.auth.presentation.state.RegisterUiState
import com.fluxpay.feature.auth.presentation.state.ResetPasswordUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/*
 * No ViewModel here receives a Context. Work runs in viewModelScope, so any in-flight
 * Retrofit call is cancelled automatically when the ViewModel is cleared.
 * On successful login the session flow flips to "logged in" and the app's root
 * navigation moves to the dashboard — the screens don't navigate themselves.
 */

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val validate: ValidateCredentialsUseCase,
    private val login: LoginUseCase,
) : ViewModel() {

    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun onEmailChange(value: String) = _state.update { it.copy(email = value, errors = it.errors.copy(email = null), errorMessage = null) }

    fun onPasswordChange(value: String) =
        _state.update { it.copy(password = value, errors = it.errors.copy(password = null), errorMessage = null) }

    fun submit() {
        val current = _state.value
        if (current.isLoading) return
        val errors = validate.login(current.email, current.password)
        if (!errors.isValid) {
            _state.update { it.copy(errors = errors) }
            return
        }
        _state.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            val result = login(current.email, current.password)
            _state.update {
                it.copy(
                    isLoading = false,
                    password = if (result is NetworkResult.Success) "" else it.password,
                    errorMessage = (result as? NetworkResult.Error)?.message,
                )
            }
        }
    }
}

@HiltViewModel
class RegisterViewModel @Inject constructor(
    private val validate: ValidateCredentialsUseCase,
    private val register: RegisterUseCase,
    observeConfig: ObservePlatformConfigUseCase,
    private val refreshConfig: RefreshPlatformConfigUseCase,
) : ViewModel() {

    private val _state = MutableStateFlow(RegisterUiState())
    val state: StateFlow<RegisterUiState> = _state.asStateFlow()

    init {
        // Currencies come from the server; keep the user's pick if it is still offered.
        observeConfig().filterNotNull().onEach { config ->
            _state.update { s ->
                val codes = config.currencies.map { it.code }
                s.copy(
                    currencies = config.currencies,
                    currency = s.currency.takeIf { it in codes } ?: config.defaultCurrency,
                    currenciesUnavailable = false,
                )
            }
        }.launchIn(viewModelScope)
        loadCurrencies()
    }

    fun loadCurrencies() {
        viewModelScope.launch {
            val failed = refreshConfig() is NetworkResult.Error
            _state.update { it.copy(currenciesUnavailable = failed && it.currencies.isEmpty()) }
        }
    }

    fun onFullNameChange(v: String) = _state.update { it.copy(fullName = v, errors = it.errors.copy(fullName = null)) }
    fun onEmailChange(v: String) = _state.update { it.copy(email = v, errors = it.errors.copy(email = null)) }
    fun onPhoneChange(v: String) = _state.update { it.copy(phone = v, errors = it.errors.copy(phone = null)) }
    fun onPasswordChange(v: String) = _state.update { it.copy(password = v, errors = it.errors.copy(password = null)) }
    fun onConfirmChange(v: String) =
        _state.update { it.copy(confirmPassword = v, errors = it.errors.copy(confirmPassword = null)) }
    fun onCurrencyChange(v: String) = _state.update { it.copy(currency = v) }

    fun submit() {
        val s = _state.value
        if (s.isLoading) return
        if (s.currency.isBlank()) {
            _state.update { it.copy(errorMessage = "Couldn't load the available currencies. Check your connection and try again.") }
            loadCurrencies()
            return
        }
        val errors = validate.register(s.fullName, s.email, s.phone, s.password, s.confirmPassword)
        if (!errors.isValid) {
            _state.update { it.copy(errors = errors) }
            return
        }
        _state.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            val result = register(s.fullName, s.email, s.phone, s.password, s.currency)
            _state.update { it.copy(isLoading = false, errorMessage = (result as? NetworkResult.Error)?.message) }
        }
    }
}

@HiltViewModel
class ForgotPasswordViewModel @Inject constructor(
    private val requestReset: RequestPasswordResetUseCase,
) : ViewModel() {

    private val _state = MutableStateFlow(ForgotPasswordUiState())
    val state: StateFlow<ForgotPasswordUiState> = _state.asStateFlow()

    fun onEmailChange(v: String) = _state.update { it.copy(email = v, emailError = null, errorMessage = null) }

    fun submit() {
        val email = _state.value.email
        if (!email.isValidEmail()) {
            _state.update { it.copy(emailError = "Enter the email you signed up with") }
            return
        }
        _state.update { it.copy(isLoading = true) }
        viewModelScope.launch {
            when (val result = requestReset(email)) {
                is NetworkResult.Success -> _state.update { it.copy(isLoading = false, sentMessage = result.data) }
                is NetworkResult.Error -> _state.update { it.copy(isLoading = false, errorMessage = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }
}

/** Opened from the email deep link fluxpay://reset-password?uid=…&token=… */
@HiltViewModel
class ResetPasswordViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val validate: ValidateCredentialsUseCase,
    private val confirmReset: ConfirmPasswordResetUseCase,
) : ViewModel() {

    private val uid: String? = savedStateHandle[AuthRoutes.ARG_UID]
    private val token: String? = savedStateHandle[AuthRoutes.ARG_TOKEN]

    private val _state = MutableStateFlow(ResetPasswordUiState(linkValid = !uid.isNullOrBlank() && !token.isNullOrBlank()))
    val state: StateFlow<ResetPasswordUiState> = _state.asStateFlow()

    fun onPasswordChange(v: String) = _state.update { it.copy(password = v, errors = FieldErrors()) }
    fun onConfirmChange(v: String) = _state.update { it.copy(confirmPassword = v, errors = FieldErrors()) }

    fun submit() {
        val s = _state.value
        if (!s.linkValid || s.isLoading || uid == null || token == null) return
        val errors = validate.newPassword(s.password, s.confirmPassword)
        if (!errors.isValid) {
            _state.update { it.copy(errors = errors) }
            return
        }
        _state.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            when (val result = confirmReset(uid, token, s.password)) {
                is NetworkResult.Success -> _state.update { it.copy(isLoading = false, successMessage = result.data) }
                is NetworkResult.Error -> _state.update { it.copy(isLoading = false, errorMessage = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }
}
