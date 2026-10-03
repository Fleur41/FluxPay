package com.fluxpay.core.data.repository

import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.result.map
import com.fluxpay.core.data.mapper.toDomain
import com.fluxpay.core.data.mapper.toEntity
import com.fluxpay.core.database.dao.TransactionDao
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionFilter
import com.fluxpay.core.domain.repository.TransactionRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.dto.TransactionDto
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

@Singleton
class TransactionRepositoryImpl @Inject constructor(
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    private val transactionDao: TransactionDao,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : TransactionRepository {

    /** Filtering runs in SQL against the local cache, so search works offline too. */
    override fun observeTransactions(filter: TransactionFilter): Flow<List<Transaction>> =
        transactionDao.observeTransactions(
            accountId = filter.accountId,
            type = filter.type?.name,
            query = filter.query?.trim()?.takeIf { it.isNotEmpty() },
            fromMillis = filter.from?.toEpochMilli(),
            toMillis = filter.to?.toEpochMilli(),
            limit = filter.limit,
        )
            .map { entities -> entities.map { it.toDomain() } }
            .flowOn(io)

    override fun observeTransaction(id: String): Flow<Transaction?> =
        transactionDao.observeTransaction(id).map { it?.toDomain() }.flowOn(io)

    /** Pulls the most recent pages from Django and replaces the local window. */
    override suspend fun refreshTransactions(): NetworkResult<Unit> = withContext(io) {
        val collected = mutableListOf<TransactionDto>()
        var page = 1
        var error: NetworkResult.Error? = null
        while (page <= MAX_PAGES) {
            val result = apiCaller { api.transactions(page = page) }
            if (result is NetworkResult.Success) {
                collected += result.data.results
                if (result.data.next == null) break
                page++
            } else {
                error = result as? NetworkResult.Error
                break
            }
        }
        val failure = error
        if (failure != null && collected.isEmpty()) return@withContext failure
        if (failure == null) {
            transactionDao.replaceAll(collected.map { it.toEntity() })
        } else {
            transactionDao.upsertAll(collected.map { it.toEntity() }) // partial: don't drop older cache
        }
        NetworkResult.Success(Unit)
    }

    override suspend fun refreshTransaction(id: String): NetworkResult<Unit> = withContext(io) {
        val result = apiCaller { api.transaction(id) }
        if (result is NetworkResult.Success) transactionDao.upsert(result.data.toEntity())
        result.map { }
    }

    private companion object {
        const val MAX_PAGES = 4 // 4 × 50 = latest 200 transactions kept offline
    }
}
