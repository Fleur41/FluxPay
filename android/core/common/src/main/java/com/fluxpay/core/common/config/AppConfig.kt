package com.fluxpay.core.common.config

/**
 * Build-variant specific values. Provided by the :app module from BuildConfig so library
 * modules stay flavor-agnostic.
 */
data class AppConfig(
    val baseUrl: String,
    val enableNetworkLogging: Boolean,
    val environment: String,
    val versionName: String,
)
