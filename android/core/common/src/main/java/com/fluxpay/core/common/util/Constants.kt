package com.fluxpay.core.common.util

/**
 * Technical constants only. Business rules (currencies, limits, the inactivity timeout, the budget
 * guideline) come from the server's GET /api/v1/config/ — see PlatformConfig.
 */
object Constants {
    const val RECENT_TRANSACTIONS_LIMIT = 5
    const val TRANSACTIONS_CACHE_LIMIT = 500

    const val DEEP_LINK_SCHEME = "fluxpay"
    const val DEEP_LINK_HOST = "fluxpay.app"
}
