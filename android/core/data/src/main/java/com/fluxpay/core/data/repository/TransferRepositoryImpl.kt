package com.fluxpay.core.data.repository

import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.result.map
import com.fluxpay.core.data.mapper.toDomain
import com.fluxpay.core.data.mapper.toEntity
import com.fluxpay.core.database.dao.TransactionDao
import com.fluxpay.core.domain.model.TransferReceipt
import com.fluxpay.core.domain.model.TransferRequest
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.domain.repository.TransferRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.dto.TransferRequestDto
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext

@Singleton
class TransferRepositoryImpl @Inject constructor(
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    private val transactionDao: TransactionDao,
    private val accountRepository: AccountRepository,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : TransferRepository {

    /** Transfers are never queued offline: money only moves when the server confirms it. */
    override suspend fun send(request: TransferRequest): NetworkResult<TransferReceipt> = withContext(io) {
        val result = apiCaller {
            api.transfer(
                TransferRequestDto(
                    sourceAccountId = request.sourceAccountId,
                    destinationAccountNumber = request.destinationAccountNumber,
                    amount = request.amount,
                    note = request.note,
                    idempotencyKey = request.idempotencyKey,
                ),
            )
        }
        if (result is NetworkResult.Success) {
            transactionDao.upsert(result.data.transaction.toEntity())
            accountRepository.refreshAccounts() // pull the new balance; cache keeps the old one if this fails
        }
        result.map { it.toDomain() }
    }
}
