package com.fluxpay.feature.auth.domain.usecase

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.util.isValidEmail
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.feature.auth.domain.model.FieldErrors
import javax.inject.Inject

/** Client-side checks that mirror the Django validators, so users get instant feedback. */
class ValidateCredentialsUseCase @Inject constructor() {

    fun login(email: String, password: String): FieldErrors = FieldErrors(
        email = emailError(email),
        password = if (password.isEmpty()) "Enter your password" else null,
    )

    fun register(fullName: String, email: String, phone: String, password: String, confirm: String): FieldErrors =
        FieldErrors(
            fullName = if (fullName.trim().length < 2) "Enter your full name" else null,
            email = emailError(email),
            phone = if (phone.isNotBlank() && !PHONE.matches(phone.trim())) "Use international format, e.g. +254712345678" else null,
            password = passwordError(password),
            confirmPassword = if (confirm != password) "Passwords don't match" else null,
        )

    fun newPassword(password: String, confirm: String) = FieldErrors(
        password = passwordError(password),
        confirmPassword = if (confirm != password) "Passwords don't match" else null,
    )

    private fun emailError(email: String) = when {
        email.isBlank() -> "Enter your email"
        !email.isValidEmail() -> "That doesn't look like an email address"
        else -> null
    }

    private fun passwordError(password: String) = when {
        password.length < 8 -> "Use at least 8 characters"
        password.all(Char::isDigit) -> "Password can't be only numbers"
        else -> null
    }

    private companion object {
        val PHONE = Regex("^\\+?[0-9]{9,15}$")
    }
}

class LoginUseCase @Inject constructor(private val authRepository: AuthRepository) {
    suspend operator fun invoke(email: String, password: String): NetworkResult<User> =
        authRepository.login(email, password)
}

class RegisterUseCase @Inject constructor(private val authRepository: AuthRepository) {
    suspend operator fun invoke(
        fullName: String,
        email: String,
        phone: String,
        password: String,
        currency: String,
    ): NetworkResult<User> = authRepository.register(fullName, email, phone, password, currency)
}

class RequestPasswordResetUseCase @Inject constructor(private val authRepository: AuthRepository) {
    suspend operator fun invoke(email: String) = authRepository.requestPasswordReset(email)
}

class ConfirmPasswordResetUseCase @Inject constructor(private val authRepository: AuthRepository) {
    suspend operator fun invoke(uid: String, token: String, newPassword: String) =
        authRepository.confirmPasswordReset(uid, token, newPassword)
}
