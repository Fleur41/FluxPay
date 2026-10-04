package com.fluxpay.feature.dashboard.domain.model

import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.Transaction
import java.math.BigDecimal

data class DashboardSummary(
    val firstName: String,
    /** The name shown to people paying you (Receive). */
    val holderName: String,
    val accounts: List<Account>,
    /** Sum of the balances held in the user's preferred currency. */
    val totalBalance: BigDecimal,
    /** Null until a wallet has synced: there is no currency to total in yet. */
    val totalCurrency: String?,
    /** Accounts in other currencies aren't converted — we just say how many there are. */
    val otherCurrencyAccounts: Int,
    val recentTransactions: List<Transaction>,
    val hideBalances: Boolean,
)
