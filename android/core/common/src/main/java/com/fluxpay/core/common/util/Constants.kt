package com.fluxpay.core.common.util

object Constants {
    /** Log the user out after this much inactivity. */
    const val SESSION_TIMEOUT_MS: Long = 5 * 60 * 1000L

    /** Show the "are you still there?" warning during the last part of the timeout. */
    const val SESSION_WARNING_MS: Long = 30 * 1000L

    const val RECENT_TRANSACTIONS_LIMIT = 5
    const val TRANSACTIONS_CACHE_LIMIT = 500

    val SUPPORTED_CURRENCIES = listOf("KES", "USD", "EUR", "GBP")
    const val DEFAULT_CURRENCY = "KES"

    const val DEEP_LINK_SCHEME = "fluxpay"
    const val DEEP_LINK_HOST = "fluxpay.app"
}
