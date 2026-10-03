package com.fluxpay.feature.auth.domain.model

data class FieldErrors(
    val fullName: String? = null,
    val email: String? = null,
    val phone: String? = null,
    val password: String? = null,
    val confirmPassword: String? = null,
) {
    val isValid: Boolean
        get() = listOf(fullName, email, phone, password, confirmPassword).all { it == null }
}
