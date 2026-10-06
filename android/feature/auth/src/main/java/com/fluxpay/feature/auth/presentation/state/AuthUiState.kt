package com.fluxpay.feature.auth.presentation.state

import com.fluxpay.core.domain.model.CurrencyRule
import com.fluxpay.feature.auth.domain.model.FieldErrors

data class LoginUiState(
    val email: String = "",
    val password: String = "",
    val errors: FieldErrors = FieldErrors(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    /** Set once the password was right and two-step verification is on: the code step is showing. */
    val mfaToken: String? = null,
    val code: String = "",
)

data class RegisterUiState(
    val fullName: String = "",
    val email: String = "",
    val phone: String = "",
    val password: String = "",
    val confirmPassword: String = "",
    /** Enabled currencies from the server's platform settings; empty until loaded. */
    val currencies: List<CurrencyRule> = emptyList(),
    val currency: String = "",
    val currenciesUnavailable: Boolean = false,
    val errors: FieldErrors = FieldErrors(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
)

data class ForgotPasswordUiState(
    val email: String = "",
    val emailError: String? = null,
    val isLoading: Boolean = false,
    val sentMessage: String? = null,
    val errorMessage: String? = null,
)

data class ResetPasswordUiState(
    val password: String = "",
    val confirmPassword: String = "",
    val errors: FieldErrors = FieldErrors(),
    val isLoading: Boolean = false,
    val linkValid: Boolean = true,
    val successMessage: String? = null,
    val errorMessage: String? = null,
)
