package com.fluxpay.core.network.interceptor

import com.fluxpay.core.common.auth.AuthTokenStore
import com.fluxpay.core.network.api.NO_AUTH_HEADER
import javax.inject.Inject
import javax.inject.Singleton
import okhttp3.Interceptor
import okhttp3.Response

/** Attaches `Authorization: Bearer <access>` to every request except the public auth endpoints. */
@Singleton
class AuthInterceptor @Inject constructor(
    private val tokenStore: AuthTokenStore,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        if (original.header(NO_AUTH_HEADER) != null) {
            return chain.proceed(original.newBuilder().removeHeader(NO_AUTH_HEADER).build())
        }
        val token = tokenStore.accessToken() ?: return chain.proceed(original)
        return chain.proceed(
            original.newBuilder()
                .header("Authorization", "Bearer $token")
                .build(),
        )
    }
}
