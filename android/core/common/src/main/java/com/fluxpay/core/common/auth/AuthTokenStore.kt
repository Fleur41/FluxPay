package com.fluxpay.core.common.auth

import kotlinx.coroutines.flow.Flow

data class AuthTokens(val access: String, val refresh: String)

/**
 * Abstraction over secure token storage. Lives in :core:common so :core:network
 * (interceptor/authenticator) can use it without depending on :core:data.
 *
 * The blocking getters are only called from OkHttp's background threads.
 */
interface AuthTokenStore {
    val isLoggedIn: Flow<Boolean>

    fun accessToken(): String?

    fun refreshToken(): String?

    suspend fun save(tokens: AuthTokens)

    suspend fun clear()
}
