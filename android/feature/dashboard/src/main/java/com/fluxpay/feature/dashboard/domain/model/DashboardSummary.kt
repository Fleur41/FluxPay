package com.fluxpay.feature.dashboard.domain.model

import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.Transaction
import java.math.BigDecimal

data class DashboardSummary(
    val firstName: String,
    val accounts: List<Account>,
    /** Sum of the balances held in the user's preferred currency. */
    val totalBalance: BigDecimal,
    val totalCurrency: String,
    /** Accounts in other currencies aren't converted — we just say how many there are. */
    val otherCurrencyAccounts: Int,
    val recentTransactions: List<Transaction>,
    val hideBalances: Boolean,
)
