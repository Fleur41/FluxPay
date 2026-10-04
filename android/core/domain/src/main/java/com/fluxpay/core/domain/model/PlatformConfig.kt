package com.fluxpay.core.domain.model

import java.math.BigDecimal

/** A currency wallets can use, with the limits staff set for it in the backend's admin. */
data class CurrencyRule(
    val code: String,
    val name: String,
    val minTransfer: BigDecimal,
    val maxTransfer: BigDecimal,
)

data class BudgetGuideline(val needsPercent: Int, val wantsPercent: Int, val savingsPercent: Int)

/**
 * Business rules from GET /api/v1/config/. The app has no built-in copies of these values:
 * screens wait for this to load (it is cached on the phone after the first successful fetch).
 */
data class PlatformConfig(
    val currencies: List<CurrencyRule>,
    val defaultCurrency: String,
    val statementMaxDays: Int,
    val sessionTimeoutMinutes: Int,
    val budgetGuideline: BudgetGuideline,
) {
    fun currency(code: String): CurrencyRule? = currencies.firstOrNull { it.code == code }
}
