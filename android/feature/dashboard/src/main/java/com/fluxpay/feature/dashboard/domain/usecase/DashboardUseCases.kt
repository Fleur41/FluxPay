package com.fluxpay.feature.dashboard.domain.usecase

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.util.Constants
import com.fluxpay.core.domain.model.TransactionFilter
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.domain.repository.PreferencesRepository
import com.fluxpay.core.domain.repository.TransactionRepository
import java.math.BigDecimal
import com.fluxpay.feature.dashboard.domain.model.DashboardSummary
import javax.inject.Inject
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine

/** Combines four offline-first streams into one dashboard model. */
class ObserveDashboardUseCase @Inject constructor(
    private val authRepository: AuthRepository,
    private val accountRepository: AccountRepository,
    private val transactionRepository: TransactionRepository,
    private val preferencesRepository: PreferencesRepository,
) {
    operator fun invoke(): Flow<DashboardSummary> = combine(
        authRepository.observeProfile(),
        accountRepository.observeAccounts(),
        transactionRepository.observeTransactions(TransactionFilter(limit = Constants.RECENT_TRANSACTIONS_LIMIT)),
        preferencesRepository.preferences,
    ) { user, accounts, recent, prefs ->
        // If no wallet matches the preferred currency, fall back to the first wallet's currency.
        val currency = accounts.firstOrNull { it.currency == prefs.currency }?.currency
            ?: accounts.firstOrNull()?.currency
        val inCurrency = accounts.filter { it.currency == currency }
        DashboardSummary(
            firstName = user?.fullName?.substringBefore(' ').orEmpty(),
            accounts = accounts,
            totalBalance = inCurrency.fold(BigDecimal.ZERO) { sum, account -> sum + account.balance },
            totalCurrency = currency,
            otherCurrencyAccounts = accounts.size - inCurrency.size,
            recentTransactions = recent,
            hideBalances = prefs.hideBalances,
        )
    }
}

/** Refreshes profile, balances and transactions in parallel; returns the first error, if any. */
class RefreshDashboardUseCase @Inject constructor(
    private val authRepository: AuthRepository,
    private val accountRepository: AccountRepository,
    private val transactionRepository: TransactionRepository,
) {
    suspend operator fun invoke(): NetworkResult<Unit> = coroutineScope {
        val profile = async { authRepository.refreshProfile() }
        val accounts = async { accountRepository.refreshAccounts() }
        val transactions = async { transactionRepository.refreshTransactions() }
        listOf(accounts.await(), transactions.await(), profile.await())
            .filterIsInstance<NetworkResult.Error>()
            .firstOrNull()
            ?: NetworkResult.Success(Unit)
    }
}

class SetHideBalancesUseCase @Inject constructor(private val preferencesRepository: PreferencesRepository) {
    suspend operator fun invoke(hide: Boolean) = preferencesRepository.setHideBalances(hide)
}
