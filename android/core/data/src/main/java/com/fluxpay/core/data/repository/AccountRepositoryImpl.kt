package com.fluxpay.core.data.repository

import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.result.map
import com.fluxpay.core.data.mapper.toDomain
import com.fluxpay.core.data.mapper.toEntity
import com.fluxpay.core.database.dao.AccountDao
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.Recipient
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

@Singleton
class AccountRepositoryImpl @Inject constructor(
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    private val accountDao: AccountDao,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : AccountRepository {

    override fun observeAccounts(): Flow<List<Account>> = accountDao.observeAccounts()
        .map { entities -> entities.map { it.toDomain() } }
        .flowOn(io)

    override suspend fun refreshAccounts(): NetworkResult<Unit> = withContext(io) {
        val result = apiCaller { api.accounts() }
        if (result is NetworkResult.Success) accountDao.replaceAll(result.data.map { it.toEntity() })
        result.map { }
    }

    override suspend fun lookupRecipient(accountNumber: String): NetworkResult<Recipient> = withContext(io) {
        apiCaller { api.lookupAccount(accountNumber) }.map { it.toDomain() }
    }
}
