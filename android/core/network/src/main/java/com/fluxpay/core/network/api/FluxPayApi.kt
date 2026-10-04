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
import com.fluxpay.core.network.dto.AmountDto
import com.fluxpay.core.network.dto.BooksSummaryDto
import com.fluxpay.core.network.dto.CashbookDto
import com.fluxpay.core.network.dto.CategoryCreateDto
import com.fluxpay.core.network.dto.CategoryDto
import com.fluxpay.core.network.dto.BookEntryDto
import com.fluxpay.core.network.dto.MyPayslipDto
import com.fluxpay.core.network.dto.NoteDto
import com.fluxpay.core.network.dto.OrganizationDto
import com.fluxpay.core.network.dto.PayRunCreateDto
import com.fluxpay.core.network.dto.PayRunDto
import com.fluxpay.core.network.dto.PayslipDto
import com.fluxpay.core.network.dto.ReasonDto
import com.fluxpay.core.network.dto.ReclassifyDto
import com.fluxpay.core.network.dto.WorkerCreateDto
import com.fluxpay.core.network.dto.WorkerDto
import com.fluxpay.core.network.dto.WorkerImportDto
import com.fluxpay.core.network.dto.WorkerImportResultDto
import com.fluxpay.core.network.dto.WorkerPatchDto
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
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

    // --- Businesses, payroll and business books --------------------------------------------

    @GET("api/v1/organizations/")
    suspend fun organizations(): List<OrganizationDto>

    @GET("api/v1/organizations/{org}/accounts/")
    suspend fun organizationAccounts(@Path("org") org: String): List<AccountDto>

    @GET("api/v1/organizations/{org}/workers/")
    suspend fun workers(
        @Path("org") org: String,
        @Query("page") page: Int = 1,
        @Query("search") search: String? = null,
    ): PageDto<WorkerDto>

    @POST("api/v1/organizations/{org}/workers/")
    suspend fun addWorker(@Path("org") org: String, @Body body: WorkerCreateDto): WorkerDto

    @POST("api/v1/organizations/{org}/workers/import/")
    suspend fun importWorkers(@Path("org") org: String, @Body body: WorkerImportDto): WorkerImportResultDto

    @PATCH("api/v1/organizations/{org}/workers/{id}/")
    suspend fun updateWorker(@Path("org") org: String, @Path("id") id: String, @Body body: WorkerPatchDto): WorkerDto

    @DELETE("api/v1/organizations/{org}/workers/{id}/")
    suspend fun removeWorker(@Path("org") org: String, @Path("id") id: String): Response<Unit>

    @GET("api/v1/organizations/{org}/pay-runs/")
    suspend fun payRuns(@Path("org") org: String, @Query("page") page: Int = 1): PageDto<PayRunDto>

    @POST("api/v1/organizations/{org}/pay-runs/")
    suspend fun createPayRun(@Path("org") org: String, @Body body: PayRunCreateDto): PayRunDto

    @GET("api/v1/organizations/{org}/pay-runs/{id}/")
    suspend fun payRun(@Path("org") org: String, @Path("id") id: String): PayRunDto

    @DELETE("api/v1/organizations/{org}/pay-runs/{id}/")
    suspend fun cancelPayRun(@Path("org") org: String, @Path("id") id: String): PayRunDto

    @PATCH("api/v1/organizations/{org}/pay-runs/{id}/payslips/{payslip}/")
    suspend fun editPayslip(
        @Path("org") org: String, @Path("id") id: String, @Path("payslip") payslip: String, @Body body: AmountDto,
    ): PayRunDto

    @DELETE("api/v1/organizations/{org}/pay-runs/{id}/payslips/{payslip}/")
    suspend fun removePayslip(@Path("org") org: String, @Path("id") id: String, @Path("payslip") payslip: String): PayRunDto

    /** action: submit, approve or reject. */
    @POST("api/v1/organizations/{org}/pay-runs/{id}/{action}/")
    suspend fun payRunAction(
        @Path("org") org: String, @Path("id") id: String, @Path("action") action: String, @Body body: NoteDto,
    ): PayRunDto

    @POST("api/v1/organizations/{org}/payslips/{payslip}/reverse/")
    suspend fun reversePayslip(@Path("org") org: String, @Path("payslip") payslip: String, @Body body: ReasonDto): PayslipDto

    @GET("api/v1/payslips/")
    suspend fun myPayslips(@Query("page") page: Int = 1): PageDto<MyPayslipDto>

    @GET("api/v1/organizations/{org}/books/cashbook/")
    suspend fun cashbook(@Path("org") org: String, @Query("start") start: String, @Query("end") end: String): CashbookDto

    @GET("api/v1/organizations/{org}/books/summary/")
    suspend fun booksSummary(@Path("org") org: String, @Query("start") start: String, @Query("end") end: String): BooksSummaryDto

    @GET("api/v1/organizations/{org}/books/categories/")
    suspend fun categories(@Path("org") org: String): List<CategoryDto>

    @POST("api/v1/organizations/{org}/books/categories/")
    suspend fun addCategory(@Path("org") org: String, @Body body: CategoryCreateDto): CategoryDto

    @PATCH("api/v1/organizations/{org}/books/entries/{id}/")
    suspend fun reclassify(@Path("org") org: String, @Path("id") id: String, @Body body: ReclassifyDto): BookEntryDto
}

/**
 * Separate, minimal API used only by the token authenticator. It runs on its own
 * OkHttpClient without the authenticator, so a failing refresh can't recurse.
 */
interface AuthRefreshApi {
    @POST("api/v1/auth/refresh/")
    fun refresh(@Body body: RefreshRequestDto): retrofit2.Call<RefreshResponseDto>
}
