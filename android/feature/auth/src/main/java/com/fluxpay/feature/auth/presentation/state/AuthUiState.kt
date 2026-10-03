package com.fluxpay.feature.auth.presentation.state

import com.fluxpay.core.common.util.Constants
import com.fluxpay.feature.auth.domain.model.FieldErrors

data class LoginUiState(
    val email: String = "",
    val password: String = "",
    val errors: FieldErrors = FieldErrors(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
)

data class RegisterUiState(
    val fullName: String = "",
    val email: String = "",
    val phone: String = "",
    val password: String = "",
    val confirmPassword: String = "",
    val currency: String = Constants.DEFAULT_CURRENCY,
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
