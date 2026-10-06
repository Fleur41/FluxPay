package com.fluxpay.core.data.repository

import com.fluxpay.core.common.auth.AuthTokenStore
import com.fluxpay.core.common.auth.AuthTokens
import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.result.map
import com.fluxpay.core.data.mapper.toDomain
import com.fluxpay.core.data.mapper.toEntity
import com.fluxpay.core.database.FluxPayDatabase
import com.fluxpay.core.database.dao.UserDao
import com.fluxpay.core.domain.model.LoginResult
import com.fluxpay.core.domain.model.MfaSetup
import com.fluxpay.core.domain.model.MfaStatus
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.domain.repository.StatementRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.dto.AuthResponseDto
import com.fluxpay.core.network.dto.LoginRequestDto
import com.fluxpay.core.network.dto.MfaLoginDto
import com.fluxpay.core.network.dto.MfaDisableDto
import com.fluxpay.core.network.dto.MfaCodeDto
import com.fluxpay.core.network.dto.PasswordResetConfirmDto
import com.fluxpay.core.network.dto.PasswordResetRequestDto
import com.fluxpay.core.network.dto.RefreshRequestDto
import com.fluxpay.core.network.dto.RegisterRequestDto
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    private val tokenStore: AuthTokenStore,
    private val userDao: UserDao,
    private val database: FluxPayDatabase,
    private val statementRepository: StatementRepository,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : AuthRepository {

    override val isLoggedIn: Flow<Boolean> = tokenStore.isLoggedIn

    override suspend fun login(email: String, password: String): NetworkResult<LoginResult> = withContext(io) {
        when (val result = apiCaller { api.login(LoginRequestDto(email.trim().lowercase(), password)) }) {
            is NetworkResult.Success -> {
                val body = result.data
                val token = body.mfaToken
                if (body.mfaRequired && token != null) {
                    NetworkResult.Success(LoginResult.NeedsCode(token))
                } else {
                    NetworkResult.Success(AuthResponseDto(checkNotNull(body.access), checkNotNull(body.refresh), checkNotNull(body.user)))
                        .persistSession().map { LoginResult.SignedIn(it) }
                }
            }
            is NetworkResult.Error -> result
            NetworkResult.Loading -> NetworkResult.Loading
        }
    }

    override suspend fun completeLogin(mfaToken: String, code: String): NetworkResult<User> = withContext(io) {
        apiCaller { api.loginMfa(MfaLoginDto(mfaToken, code.trim())) }.persistSession()
    }

    override suspend fun mfaStatus() = withContext(io) {
        apiCaller { api.mfaStatus() }.map { MfaStatus(it.enabled, it.required, it.recoveryCodesLeft) }
    }

    override suspend fun startMfaSetup() = withContext(io) {
        apiCaller { api.mfaSetup() }.map { MfaSetup(it.secret, it.otpauthUri) }
    }

    override suspend fun enableMfa(code: String) = withContext(io) {
        apiCaller { api.mfaEnable(MfaCodeDto(code.trim())) }.map { it.recoveryCodes }
    }

    override suspend fun disableMfa(password: String, code: String) = withContext(io) {
        apiCaller { api.mfaDisable(MfaDisableDto(password, code.trim())) }.map { }
    }

    override suspend fun newRecoveryCodes(code: String) = withContext(io) {
        apiCaller { api.mfaRecoveryCodes(MfaCodeDto(code.trim())) }.map { it.recoveryCodes }
    }

    override suspend fun register(
        fullName: String,
        email: String,
        phoneNumber: String,
        password: String,
        currency: String,
    ): NetworkResult<User> = withContext(io) {
        apiCaller {
            api.register(
                RegisterRequestDto(
                    email = email.trim().lowercase(),
                    fullName = fullName.trim(),
                    phoneNumber = phoneNumber.trim(),
                    password = password,
                    currency = currency,
                ),
            )
        }.persistSession()
    }

    override suspend fun logout(revokeRemotely: Boolean) = withContext(io) {
        if (revokeRemotely) {
            tokenStore.refreshToken()?.let { refresh -> apiCaller { api.logout(RefreshRequestDto(refresh)) } }
        }
        tokenStore.clear()
        // Wipe every cached balance/transaction (and the budget planner) so the next user of this phone
        // sees nothing, plus any downloaded statements.
        database.clearAllTables()
        statementRepository.clearDownloads()
    }

    override suspend fun requestPasswordReset(email: String): NetworkResult<String> = withContext(io) {
        apiCaller { api.requestPasswordReset(PasswordResetRequestDto(email.trim().lowercase())) }.map { it.detail }
    }

    override suspend fun confirmPasswordReset(uid: String, token: String, newPassword: String): NetworkResult<String> =
        withContext(io) {
            apiCaller { api.confirmPasswordReset(PasswordResetConfirmDto(uid, token, newPassword)) }.map { it.detail }
        }

    override fun observeProfile(): Flow<User?> = userDao.observeUser().map { it?.toDomain() }

    override suspend fun refreshProfile(): NetworkResult<User> = withContext(io) {
        val result = apiCaller { api.me() }
        if (result is NetworkResult.Success) userDao.upsert(result.data.toEntity())
        result.map { it.toEntity().toDomain() }
    }

    private suspend fun NetworkResult<AuthResponseDto>.persistSession(): NetworkResult<User> {
        if (this is NetworkResult.Success) {
            database.clearAllTables() // never mix a previous user's cache with the new one
            tokenStore.save(AuthTokens(access = data.access, refresh = data.refresh))
            userDao.upsert(data.user.toEntity())
        }
        return map { it.user.toEntity().toDomain() }
    }
}
