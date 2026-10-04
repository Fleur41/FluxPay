package com.fluxpay.feature.transactions.domain.usecase

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.DownloadedStatement
import com.fluxpay.core.domain.model.StatementFormat
import com.fluxpay.core.domain.model.StatementPeriod
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionFilter
import com.fluxpay.core.domain.repository.StatementRepository
import com.fluxpay.core.domain.repository.TransactionRepository
import com.fluxpay.feature.transactions.domain.model.TypeFilter
import javax.inject.Inject
import kotlinx.coroutines.flow.Flow

/** Search + type filtering run as SQL against the Room cache, so they work offline. */
class ObserveFilteredTransactionsUseCase @Inject constructor(
    private val repository: TransactionRepository,
) {
    operator fun invoke(query: String, typeFilter: TypeFilter): Flow<List<Transaction>> =
        repository.observeTransactions(
            TransactionFilter(
                type = typeFilter.type,
                query = query.trim().takeIf { it.length >= MIN_QUERY_LENGTH },
            ),
        )

    private companion object {
        const val MIN_QUERY_LENGTH = 2
    }
}

class RefreshTransactionsUseCase @Inject constructor(private val repository: TransactionRepository) {
    suspend operator fun invoke(): NetworkResult<Unit> = repository.refreshTransactions()
}

class ObserveTransactionUseCase @Inject constructor(private val repository: TransactionRepository) {
    operator fun invoke(id: String): Flow<Transaction?> = repository.observeTransaction(id)
}

class RefreshTransactionUseCase @Inject constructor(private val repository: TransactionRepository) {
    suspend operator fun invoke(id: String): NetworkResult<Unit> = repository.refreshTransaction(id)
}

class DownloadStatementUseCase @Inject constructor(private val repository: StatementRepository) {
    suspend operator fun invoke(period: StatementPeriod, format: StatementFormat): NetworkResult<DownloadedStatement> =
        repository.download(period, format)
}
