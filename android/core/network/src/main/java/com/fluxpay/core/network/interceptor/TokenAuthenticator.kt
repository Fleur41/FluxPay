package com.fluxpay.core.network.interceptor

import com.fluxpay.core.common.auth.AuthTokenStore
import com.fluxpay.core.common.auth.AuthTokens
import com.fluxpay.core.network.api.AuthRefreshApi
import com.fluxpay.core.network.dto.RefreshRequestDto
import javax.inject.Inject
import javax.inject.Provider
import javax.inject.Singleton
import kotlinx.coroutines.runBlocking
import okhttp3.Authenticator
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route

/**
 * Called by OkHttp when the API answers 401. Refreshes the access token once (SimpleJWT
 * rotates the refresh token too) and retries; if refreshing fails the session is cleared,
 * which the app observes and sends the user back to login.
 */
@Singleton
class TokenAuthenticator @Inject constructor(
    private val tokenStore: AuthTokenStore,
    // Provider breaks the OkHttpClient -> Authenticator -> Retrofit cycle.
    private val refreshApi: Provider<AuthRefreshApi>,
) : Authenticator {

    private val lock = Any()

    override fun authenticate(route: Route?, response: Response): Request? {
        if (responseCount(response) >= 2) return null // already retried once
        val failedToken = response.request.header("Authorization")?.removePrefix("Bearer ")
            ?: return null // request wasn't authenticated in the first place

        synchronized(lock) {
            val current = tokenStore.accessToken()
            // Another thread already refreshed while we were waiting: just retry.
            if (current != null && current != failedToken) return response.request.withToken(current)

            val refresh = tokenStore.refreshToken()
            if (refresh == null) {
                clearSession()
                return null
            }
            val result = runCatching { refreshApi.get().refresh(RefreshRequestDto(refresh)).execute() }.getOrNull()
            val body = result?.body()
            if (result == null || !result.isSuccessful || body == null) {
                // Network error: keep the session so the user can retry. Rejected token: log out.
                if (result != null && result.code() in 400..499) clearSession()
                return null
            }
            runBlocking { tokenStore.save(AuthTokens(access = body.access, refresh = body.refresh ?: refresh)) }
            return response.request.withToken(body.access)
        }
    }

    private fun clearSession() = runBlocking { tokenStore.clear() }

    private fun Request.withToken(token: String) = newBuilder().header("Authorization", "Bearer $token").build()

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
