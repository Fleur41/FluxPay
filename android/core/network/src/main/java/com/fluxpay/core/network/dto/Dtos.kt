package com.fluxpay.core.network.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass
import java.math.BigDecimal
import java.time.Instant

// Data Transfer Objects mirroring the Django REST Framework serializers 1:1.
// They never leave :core:network / :core:data — mappers adapt them to domain models.

@JsonClass(generateAdapter = true)
data class UserDto(
    val id: String,
    val email: String,
    @Json(name = "full_name") val fullName: String,
    @Json(name = "phone_number") val phoneNumber: String = "",
)

@JsonClass(generateAdapter = true)
data class LoginRequestDto(val email: String, val password: String)

@JsonClass(generateAdapter = true)
data class RegisterRequestDto(
    val email: String,
    @Json(name = "full_name") val fullName: String,
    @Json(name = "phone_number") val phoneNumber: String,
    val password: String,
    val currency: String,
)

@JsonClass(generateAdapter = true)
data class AuthResponseDto(
    val access: String,
    val refresh: String,
    val user: UserDto,
)

@JsonClass(generateAdapter = true)
data class RefreshRequestDto(val refresh: String)

@JsonClass(generateAdapter = true)
data class RefreshResponseDto(val access: String, val refresh: String? = null)

@JsonClass(generateAdapter = true)
data class PasswordResetRequestDto(val email: String)

@JsonClass(generateAdapter = true)
data class PasswordResetConfirmDto(
    val uid: String,
    val token: String,
    @Json(name = "new_password") val newPassword: String,
)

@JsonClass(generateAdapter = true)
data class DetailResponseDto(val detail: String)

@JsonClass(generateAdapter = true)
data class AccountDto(
    val id: String,
    @Json(name = "account_number") val accountNumber: String,
    val name: String,
    val currency: String,
    val balance: BigDecimal,
    @Json(name = "updated_at") val updatedAt: Instant,
)

@JsonClass(generateAdapter = true)
data class RecipientDto(
    @Json(name = "account_number") val accountNumber: String,
    val currency: String,
    @Json(name = "holder_name") val holderName: String,
)

@JsonClass(generateAdapter = true)
data class TransactionDto(
    val id: String,
    @Json(name = "account_id") val accountId: String,
    val type: String,
    val category: String,
    val status: String,
    val amount: BigDecimal,
    val currency: String,
    @Json(name = "balance_after") val balanceAfter: BigDecimal,
    @Json(name = "counterparty_name") val counterpartyName: String = "",
    @Json(name = "counterparty_account") val counterpartyAccount: String = "",
    val description: String = "",
    val reference: String,
    @Json(name = "created_at") val createdAt: Instant,
)

@JsonClass(generateAdapter = true)
data class PageDto<T>(
    val count: Int,
    val next: String?,
    val previous: String?,
    val results: List<T>,
)

@JsonClass(generateAdapter = true)
data class TransferRequestDto(
    @Json(name = "source_account_id") val sourceAccountId: String,
    @Json(name = "destination_account_number") val destinationAccountNumber: String,
    val amount: BigDecimal,
    val note: String,
    @Json(name = "idempotency_key") val idempotencyKey: String,
)

@JsonClass(generateAdapter = true)
data class TransferDto(
    val id: String,
    val reference: String,
    val amount: BigDecimal,
    val currency: String,
    val note: String,
    @Json(name = "destination_account_number") val destinationAccountNumber: String,
    @Json(name = "recipient_name") val recipientName: String,
    @Json(name = "created_at") val createdAt: Instant,
)

@JsonClass(generateAdapter = true)
data class TransferResponseDto(
    val transfer: TransferDto,
    val transaction: TransactionDto,
)

/** Django error envelope: {"error": {"code": "...", "message": "..."}} */
@JsonClass(generateAdapter = true)
data class ErrorEnvelopeDto(val error: ErrorBodyDto)

@JsonClass(generateAdapter = true)
data class ErrorBodyDto(val code: String = "error", val message: String = "Something went wrong")
