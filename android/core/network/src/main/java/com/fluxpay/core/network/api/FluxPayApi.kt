package com.fluxpay.core.network.api

import com.fluxpay.core.network.dto.AccountDto
import com.fluxpay.core.network.dto.AmountDto
import com.fluxpay.core.network.dto.AuthResponseDto
import com.fluxpay.core.network.dto.BeneficiaryDto
import com.fluxpay.core.network.dto.BookEntryDto
import com.fluxpay.core.network.dto.BooksSummaryDto
import com.fluxpay.core.network.dto.BusinessPaymentCreateDto
import com.fluxpay.core.network.dto.BusinessPaymentDto
import com.fluxpay.core.network.dto.CashbookDto
import com.fluxpay.core.network.dto.CategoryCreateDto
import com.fluxpay.core.network.dto.CategoryDto
import com.fluxpay.core.network.dto.CodeDto
import com.fluxpay.core.network.dto.DetailResponseDto
import com.fluxpay.core.network.dto.EmployerDto
import com.fluxpay.core.network.dto.ExternalPaymentDto
import com.fluxpay.core.network.dto.InvitationPreviewDto
import com.fluxpay.core.network.dto.InvoiceCreateDto
import com.fluxpay.core.network.dto.InvoiceDto
import com.fluxpay.core.network.dto.InvoiceListDto
import com.fluxpay.core.network.dto.InvoicePayDto
import com.fluxpay.core.network.dto.JoinCodeDto
import com.fluxpay.core.network.dto.LoginRequestDto
import com.fluxpay.core.network.dto.LoginResponseDto
import com.fluxpay.core.network.dto.MemberDto
import com.fluxpay.core.network.dto.MfaCodeDto
import com.fluxpay.core.network.dto.MfaDisableDto
import com.fluxpay.core.network.dto.MfaLoginDto
import com.fluxpay.core.network.dto.MfaSetupDto
import com.fluxpay.core.network.dto.MfaStatusDto
import com.fluxpay.core.network.dto.MpesaWithdrawalDto
import com.fluxpay.core.network.dto.MyPayslipDto
import com.fluxpay.core.network.dto.NoteDto
import com.fluxpay.core.network.dto.NotificationSettingsDto
import com.fluxpay.core.network.dto.NotificationSettingsPatchDto
import com.fluxpay.core.network.dto.OrganizationCreateDto
import com.fluxpay.core.network.dto.OrganizationDto
import com.fluxpay.core.network.dto.OrganizationPatchDto
import com.fluxpay.core.network.dto.PageDto
import com.fluxpay.core.network.dto.PasswordResetConfirmDto
import com.fluxpay.core.network.dto.PasswordResetRequestDto
import com.fluxpay.core.network.dto.PayRunCreateDto
import com.fluxpay.core.network.dto.PayRunDto
import com.fluxpay.core.network.dto.PayslipDto
import com.fluxpay.core.network.dto.PlatformConfigDto
import com.fluxpay.core.network.dto.ReasonDto
import com.fluxpay.core.network.dto.RecipientDto
import com.fluxpay.core.network.dto.ReclassifyDto
import com.fluxpay.core.network.dto.RecoveryCodesDto
import com.fluxpay.core.network.dto.RefreshRequestDto
import com.fluxpay.core.network.dto.RefreshResponseDto
import com.fluxpay.core.network.dto.RegisterRequestDto
import com.fluxpay.core.network.dto.RoleDto
import com.fluxpay.core.network.dto.TeamInvitationDto
import com.fluxpay.core.network.dto.TeamInviteDto
import com.fluxpay.core.network.dto.TokenDto
import com.fluxpay.core.network.dto.TransactionDto
import com.fluxpay.core.network.dto.TransferRequestDto
import com.fluxpay.core.network.dto.TransferResponseDto
import com.fluxpay.core.network.dto.UserDto
import com.fluxpay.core.network.dto.WorkerActionDto
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
    suspend fun login(@Body body: LoginRequestDto): LoginResponseDto

    /** The second step of signing in, with a code from the authenticator app or a recovery code. */
    @POST("api/v1/auth/login/mfa/")
    suspend fun loginMfa(@Body body: MfaLoginDto): AuthResponseDto

    @GET("api/v1/auth/mfa/")
    suspend fun mfaStatus(): MfaStatusDto

    @POST("api/v1/auth/mfa/setup/")
    suspend fun mfaSetup(): MfaSetupDto

    @POST("api/v1/auth/mfa/enable/")
    suspend fun mfaEnable(@Body body: MfaCodeDto): RecoveryCodesDto

    @POST("api/v1/auth/mfa/disable/")
    suspend fun mfaDisable(@Body body: MfaDisableDto): Response<Unit>

    @POST("api/v1/auth/mfa/recovery-codes/")
    suspend fun mfaRecoveryCodes(@Body body: MfaCodeDto): RecoveryCodesDto

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

    /** The money leaves the wallet now; M-Pesa confirms later (or it comes back). Answers 202. */
    @POST("api/v1/withdrawals/mpesa/")
    suspend fun withdrawToMpesa(@Body body: MpesaWithdrawalDto): ExternalPaymentDto

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

    /** Owners only: e.g. the approval limit above which a second person must approve payments. */
    @PATCH("api/v1/organizations/{org}/")
    suspend fun updateOrganization(@Path("org") org: String, @Body body: OrganizationPatchDto): OrganizationDto

    /** The caller becomes its owner; the business wallet opens with it. */
    @POST("api/v1/organizations/")
    suspend fun createOrganization(@Body body: OrganizationCreateDto): OrganizationDto

    @GET("api/v1/organizations/{org}/members/")
    suspend fun members(@Path("org") org: String): List<MemberDto>

    @PATCH("api/v1/organizations/{org}/members/{id}/")
    suspend fun changeRole(@Path("org") org: String, @Path("id") id: String, @Body body: RoleDto): MemberDto

    /** Removes a member, or leaves the business when it's the caller's own membership. */
    @DELETE("api/v1/organizations/{org}/members/{id}/")
    suspend fun removeMember(@Path("org") org: String, @Path("id") id: String): Response<Unit>

    /** Pending invitations (owners and admins). */
    @GET("api/v1/organizations/{org}/invitations/")
    suspend fun teamInvitations(@Path("org") org: String): List<TeamInvitationDto>

    @POST("api/v1/organizations/{org}/invitations/")
    suspend fun inviteMember(@Path("org") org: String, @Body body: TeamInviteDto): TeamInvitationDto

    @DELETE("api/v1/organizations/{org}/invitations/{id}/")
    suspend fun revokeTeamInvitation(@Path("org") org: String, @Path("id") id: String): Response<Unit>

    /** The token from the emailed link (fluxpay://join-business?token=…); returns the business joined. */
    @POST("api/v1/invitations/accept/")
    suspend fun acceptTeamInvitation(@Body body: TokenDto): OrganizationDto

    @GET("api/v1/organizations/{org}/accounts/")
    suspend fun organizationAccounts(@Path("org") org: String): List<AccountDto>

    @GET("api/v1/organizations/{org}/workers/")
    suspend fun workers(
        @Path("org") org: String,
        @Query("page") page: Int = 1,
        @Query("search") search: String? = null,
        @Query("active") active: String? = null, // "all": every status, not just active workers
    ): PageDto<WorkerDto>

    /** approve, decline, suspend, reactivate or resend-invitation. */
    @POST("api/v1/organizations/{org}/workers/{id}/{action}/")
    suspend fun workerAction(
        @Path("org") org: String,
        @Path("id") id: String,
        @Path("action") action: String,
        @Body body: WorkerActionDto,
    ): WorkerDto

    @GET("api/v1/organizations/{org}/worker-join-code/")
    suspend fun joinCode(@Path("org") org: String): JoinCodeDto

    /** A new join code; the old one stops working. */
    @POST("api/v1/organizations/{org}/worker-join-code/")
    suspend fun newJoinCode(@Path("org") org: String): JoinCodeDto

    @DELETE("api/v1/organizations/{org}/worker-join-code/")
    suspend fun disableJoinCode(@Path("org") org: String): JoinCodeDto

    @POST("api/v1/worker-invitations/preview/")
    suspend fun previewInvitation(@Body body: CodeDto): InvitationPreviewDto

    @POST("api/v1/worker-invitations/accept/")
    suspend fun acceptInvitation(@Body body: CodeDto): EmployerDto

    @GET("api/v1/employers/")
    suspend fun myEmployers(): List<EmployerDto>

    @POST("api/v1/employers/join/")
    suspend fun requestToJoin(@Body body: CodeDto): EmployerDto

    @POST("api/v1/employers/{id}/leave/")
    suspend fun leaveEmployer(@Path("id") id: String): EmployerDto

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

    /** Saved suppliers, contractors, the landlord... (`active=all` would include archived ones). */
    @GET("api/v1/organizations/{org}/beneficiaries/")
    suspend fun beneficiaries(@Path("org") org: String, @Query("page") page: Int = 1): PageDto<BeneficiaryDto>

    /** name, kind, method and that method's details (account_number, mpesa_phone, paybill_number...). */
    @POST("api/v1/organizations/{org}/beneficiaries/")
    suspend fun addBeneficiary(@Path("org") org: String, @Body body: Map<String, String>): BeneficiaryDto

    /** An owner or admin (not the one who entered them) confirms the payout details. */
    @POST("api/v1/organizations/{org}/beneficiaries/{id}/verify/")
    suspend fun verifyBeneficiary(@Path("org") org: String, @Path("id") id: String): BeneficiaryDto

    @DELETE("api/v1/organizations/{org}/beneficiaries/{id}/")
    suspend fun archiveBeneficiary(@Path("org") org: String, @Path("id") id: String): BeneficiaryDto

    /** Payments out of the cashbook made on their own (not pay-run salaries). */
    @GET("api/v1/organizations/{org}/payments/")
    suspend fun businessPayments(
        @Path("org") org: String,
        @Query("pay_run") payRun: String = "none",
        @Query("page") page: Int = 1,
    ): PageDto<BusinessPaymentDto>

    /** Up to the approval limit it goes straight out; above it, it waits for an owner or admin. */
    @POST("api/v1/organizations/{org}/payments/")
    suspend fun createBusinessPayment(@Path("org") org: String, @Body body: BusinessPaymentCreateDto): BusinessPaymentDto

    /** action: approve, reject or cancel. */
    @POST("api/v1/organizations/{org}/payments/{id}/{action}/")
    suspend fun businessPaymentAction(
        @Path("org") org: String, @Path("id") id: String, @Path("action") action: String, @Body body: NoteDto,
    ): BusinessPaymentDto

    /** Bills and invoices, with what's owed each way. open = "1": only those not fully paid. */
    @GET("api/v1/organizations/{org}/books/invoices/")
    suspend fun invoices(@Path("org") org: String, @Query("open") open: String? = null): InvoiceListDto

    @POST("api/v1/organizations/{org}/books/invoices/")
    suspend fun createInvoice(@Path("org") org: String, @Body body: InvoiceCreateDto): InvoiceDto

    /** Cashbook entries that could pay this bill (or collect this invoice). */
    @GET("api/v1/organizations/{org}/books/invoices/{id}/payable-entries/")
    suspend fun payableEntries(@Path("org") org: String, @Path("id") id: String): List<BookEntryDto>

    @POST("api/v1/organizations/{org}/books/invoices/{id}/pay/")
    suspend fun payInvoice(@Path("org") org: String, @Path("id") id: String, @Body body: InvoicePayDto): InvoiceDto

    @POST("api/v1/organizations/{org}/books/invoices/{id}/cancel/")
    suspend fun cancelInvoice(@Path("org") org: String, @Path("id") id: String, @Body body: ReasonDto): InvoiceDto

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
