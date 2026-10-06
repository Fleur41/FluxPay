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

/**
 * The answer to email + password: the tokens, or (with two-step verification on) a challenge to exchange with a
 * code at auth/login/mfa/.
 */
@JsonClass(generateAdapter = true)
data class LoginResponseDto(
    val access: String? = null,
    val refresh: String? = null,
    val user: UserDto? = null,
    @Json(name = "mfa_required") val mfaRequired: Boolean = false,
    @Json(name = "mfa_token") val mfaToken: String? = null,
)

@JsonClass(generateAdapter = true)
data class MfaLoginDto(@Json(name = "mfa_token") val mfaToken: String, val code: String)

@JsonClass(generateAdapter = true)
data class MfaStatusDto(
    val enabled: Boolean,
    val required: Boolean,
    @Json(name = "recovery_codes_left") val recoveryCodesLeft: Int = 0,
)

@JsonClass(generateAdapter = true)
data class MfaSetupDto(val secret: String, @Json(name = "otpauth_uri") val otpauthUri: String)

@JsonClass(generateAdapter = true)
data class MfaCodeDto(val code: String)

@JsonClass(generateAdapter = true)
data class MfaDisableDto(val password: String, val code: String)

@JsonClass(generateAdapter = true)
data class RecoveryCodesDto(@Json(name = "recovery_codes") val recoveryCodes: List<String>)

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

@JsonClass(generateAdapter = true)
data class NotificationSettingsDto(
    @Json(name = "email_enabled") val emailEnabled: Boolean,
    @Json(name = "sms_enabled") val smsEnabled: Boolean,
)

/** PATCH body: Moshi leaves out null fields, so only the changed switch is sent. */
@JsonClass(generateAdapter = true)
data class NotificationSettingsPatchDto(
    @Json(name = "email_enabled") val emailEnabled: Boolean? = null,
    @Json(name = "sms_enabled") val smsEnabled: Boolean? = null,
)

@JsonClass(generateAdapter = true)
data class CurrencyRuleDto(
    val code: String,
    val name: String,
    @Json(name = "min_transfer") val minTransfer: BigDecimal,
    @Json(name = "max_transfer") val maxTransfer: BigDecimal,
)

@JsonClass(generateAdapter = true)
data class PlatformConfigDto(
    val currencies: List<CurrencyRuleDto>,
    @Json(name = "default_currency") val defaultCurrency: String,
    @Json(name = "statement_max_days") val statementMaxDays: Int,
    @Json(name = "session_timeout_minutes") val sessionTimeoutMinutes: Int,
    @Json(name = "budget_guideline") val budgetGuideline: Map<String, Int>,
)

/** Sends money from one of the user's wallets to their own M-Pesa number (the one on their profile). */
@JsonClass(generateAdapter = true)
data class MpesaWithdrawalDto(
    @Json(name = "account_id") val accountId: String,
    val amount: String,
    @Json(name = "idempotency_key") val idempotencyKey: String,
)

/** A payment to or from M-Pesa or a bank; it completes later, when the provider confirms it. */
@JsonClass(generateAdapter = true)
data class ExternalPaymentDto(
    val id: String,
    val status: String,
    val amount: java.math.BigDecimal,
    val currency: String,
    val reference: String,
    @Json(name = "failure_reason") val failureReason: String? = null,
)
