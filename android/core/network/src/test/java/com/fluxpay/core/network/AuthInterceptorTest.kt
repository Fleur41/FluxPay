package com.fluxpay.core.network

import com.fluxpay.core.common.auth.AuthTokenStore
import com.fluxpay.core.common.auth.AuthTokens
import com.fluxpay.core.network.adapter.BigDecimalAdapter
import com.fluxpay.core.network.adapter.InstantAdapter
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.dto.LoginRequestDto
import com.fluxpay.core.network.interceptor.AuthInterceptor
import com.squareup.moshi.Moshi
import java.math.BigDecimal
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

class AuthInterceptorTest {

    private class FakeTokenStore(var access: String?) : AuthTokenStore {
        override val isLoggedIn = MutableStateFlow(access != null)
        override fun accessToken() = access
        override fun refreshToken() = "refresh"
        override suspend fun save(tokens: AuthTokens) { access = tokens.access }
        override suspend fun clear() { access = null }
    }

    private val server = MockWebServer()
    private val moshi = Moshi.Builder().add(BigDecimalAdapter()).add(InstantAdapter()).build()
    private lateinit var api: FluxPayApi

    @Before
    fun setUp() {
        server.start()
        val client = OkHttpClient.Builder().addInterceptor(AuthInterceptor(FakeTokenStore("abc123"))).build()
        api = Retrofit.Builder()
            .baseUrl(server.url("/"))
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(FluxPayApi::class.java)
    }

    @After
    fun tearDown() = server.shutdown()

    @Test
    fun `attaches bearer token to protected endpoints and parses money as BigDecimal`() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """[{"id":"a1","account_number":"1234567890","name":"Main","currency":"KES",
                   "balance":"10000.10","updated_at":"2026-10-03T11:26:00.123456Z"}]""",
            ),
        )
        val accounts = api.accounts()
        assertEquals(BigDecimal("10000.10"), accounts.single().balance)
        assertEquals("Bearer abc123", server.takeRequest().getHeader("Authorization"))
    }

    @Test
    fun `skips token and strips marker header on public endpoints`() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """{"access":"a","refresh":"r","user":{"id":"u","email":"e@x.com","full_name":"E X"}}""",
            ),
        )
        api.login(LoginRequestDto("e@x.com", "pw"))
        val request = server.takeRequest()
        assertNull(request.getHeader("Authorization"))
        assertTrue(request.headers.names().none { it.startsWith("X-FluxPay") })
    }
}
