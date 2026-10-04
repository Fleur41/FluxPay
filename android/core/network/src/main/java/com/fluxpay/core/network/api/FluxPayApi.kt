package com.fluxpay.core.network.api

import com.fluxpay.core.network.dto.AccountDto
import com.fluxpay.core.network.dto.AuthResponseDto
import com.fluxpay.core.network.dto.DetailResponseDto
import com.fluxpay.core.network.dto.LoginRequestDto
import com.fluxpay.core.network.dto.NotificationSettingsDto
import com.fluxpay.core.network.dto.NotificationSettingsPatchDto
import com.fluxpay.core.network.dto.PageDto
import com.fluxpay.core.network.dto.PasswordResetConfirmDto
import com.fluxpay.core.network.dto.PlatformConfigDto
import com.fluxpay.core.network.dto.PasswordResetRequestDto
import com.fluxpay.core.network.dto.RecipientDto
import com.fluxpay.core.network.dto.RefreshRequestDto
import com.fluxpay.core.network.dto.RefreshResponseDto
import com.fluxpay.core.network.dto.RegisterRequestDto
import com.fluxpay.core.network.dto.TransactionDto
import com.fluxpay.core.network.dto.TransferRequestDto
import com.fluxpay.core.network.dto.TransferResponseDto
import com.fluxpay.core.network.dto.UserDto
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Headers
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

/** Marker header: the [com.fluxpay.core.network.interceptor.AuthInterceptor] skips the JWT for these calls. */
const val NO_AUTH_HEADER = "X-FluxPay-No-Auth"
private const val NO_AUTH = "$NO_AUTH_HEADER: true"

/** Django REST Framework endpoints (backend/ in this repo). */
interface FluxPayApi {

    /** Public: the sign-up screen needs the currency list before anyone is signed in. */
    @Headers(NO_AUTH)
    @GET("api/v1/config/")
    suspend fun config(): PlatformConfigDto

    @Headers(NO_AUTH)
    @POST("api/v1/auth/login/")
    suspend fun login(@Body body: LoginRequestDto): AuthResponseDto

    @Headers(NO_AUTH)
    @POST("api/v1/auth/register/")
    suspend fun register(@Body body: RegisterRequestDto): AuthResponseDto

    @POST("api/v1/auth/logout/")
    suspend fun logout(@Body body: RefreshRequestDto)

    @GET("api/v1/auth/me/")
    suspend fun me(): UserDto

    @Headers(NO_AUTH)
    @POST("api/v1/auth/password-reset/")
    suspend fun requestPasswordReset(@Body body: PasswordResetRequestDto): DetailResponseDto

    @Headers(NO_AUTH)
    @POST("api/v1/auth/password-reset/confirm/")
    suspend fun confirmPasswordReset(@Body body: PasswordResetConfirmDto): DetailResponseDto

    @GET("api/v1/accounts/")
    suspend fun accounts(): List<AccountDto>

    @GET("api/v1/accounts/lookup/")
    suspend fun lookupAccount(@Query("account_number") accountNumber: String): RecipientDto

    @GET("api/v1/transactions/")
    suspend fun transactions(
        @Query("page") page: Int = 1,
        @Query("account") accountId: String? = null,
        @Query("type") type: String? = null,
        @Query("search") search: String? = null,
    ): PageDto<TransactionDto>

    @GET("api/v1/transactions/{id}/")
    suspend fun transaction(@Path("id") id: String): TransactionDto

    @POST("api/v1/transfers/")
    suspend fun transfer(@Body body: TransferRequestDto): TransferResponseDto

    @GET("api/v1/notifications/settings/")
    suspend fun notificationSettings(): NotificationSettingsDto

    @PATCH("api/v1/notifications/settings/")
    suspend fun updateNotificationSettings(@Body body: NotificationSettingsPatchDto): NotificationSettingsDto

    /** A PDF or CSV file. `file_format`, not `format`: DRF reserves `format` for content negotiation. */
    @Streaming
    @GET("api/v1/statements/")
    suspend fun statement(
        @Query("date_from") dateFrom: String,
        @Query("date_to") dateTo: String,
        @Query("file_format") fileFormat: String,
    ): Response<ResponseBody>
}

/**
 * Separate, minimal API used only by the token authenticator. It runs on its own
 * OkHttpClient without the authenticator, so a failing refresh can't recurse.
 */
interface AuthRefreshApi {
    @POST("api/v1/auth/refresh/")
    fun refresh(@Body body: RefreshRequestDto): retrofit2.Call<RefreshResponseDto>
}
