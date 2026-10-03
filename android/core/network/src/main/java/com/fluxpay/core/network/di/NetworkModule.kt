package com.fluxpay.core.network.di

import com.fluxpay.core.common.config.AppConfig
import com.fluxpay.core.network.adapter.BigDecimalAdapter
import com.fluxpay.core.network.adapter.InstantAdapter
import com.fluxpay.core.network.api.AuthRefreshApi
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.interceptor.AuthInterceptor
import com.fluxpay.core.network.interceptor.TokenAuthenticator
import com.squareup.moshi.Moshi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import java.util.concurrent.TimeUnit
import javax.inject.Qualifier
import javax.inject.Singleton
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class BaseClient

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideMoshi(): Moshi = Moshi.Builder()
        .add(BigDecimalAdapter())
        .add(InstantAdapter())
        .build()

    /** Shared base: timeouts + logging. Both clients below derive from it (and share its connection pool). */
    @Provides
    @Singleton
    @BaseClient
    fun provideBaseOkHttpClient(config: AppConfig): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .apply {
            if (config.enableNetworkLogging) {
                addInterceptor(
                    HttpLoggingInterceptor().apply {
                        level = HttpLoggingInterceptor.Level.BODY
                        redactHeader("Authorization")
                    },
                )
            }
        }
        .build()

    @Provides
    @Singleton
    fun provideOkHttpClient(
        @BaseClient base: OkHttpClient,
        authInterceptor: AuthInterceptor,
        tokenAuthenticator: TokenAuthenticator,
    ): OkHttpClient = base.newBuilder()
        .addInterceptor(authInterceptor)
        .authenticator(tokenAuthenticator)
        .build()

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient, moshi: Moshi, config: AppConfig): Retrofit = Retrofit.Builder()
        .baseUrl(config.baseUrl.ensureTrailingSlash())
        .client(client)
        .addConverterFactory(MoshiConverterFactory.create(moshi))
        .build()

    @Provides
    @Singleton
    fun provideFluxPayApi(retrofit: Retrofit): FluxPayApi = retrofit.create(FluxPayApi::class.java)

    @Provides
    @Singleton
    fun provideAuthRefreshApi(@BaseClient base: OkHttpClient, moshi: Moshi, config: AppConfig): AuthRefreshApi =
        Retrofit.Builder()
            .baseUrl(config.baseUrl.ensureTrailingSlash())
            .client(base)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(AuthRefreshApi::class.java)

    private fun String.ensureTrailingSlash() = if (endsWith("/")) this else "$this/"
}
