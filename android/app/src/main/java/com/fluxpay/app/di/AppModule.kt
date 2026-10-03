package com.fluxpay.app.di

import com.fluxpay.app.BuildConfig
import com.fluxpay.core.common.config.AppConfig
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/** Bridges flavor-specific BuildConfig values into the flavor-agnostic library modules. */
@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideAppConfig(): AppConfig = AppConfig(
        baseUrl = BuildConfig.BASE_URL,
        enableNetworkLogging = BuildConfig.ENABLE_LOGGING,
        environment = BuildConfig.FLAVOR,
        versionName = BuildConfig.VERSION_NAME,
    )
}
