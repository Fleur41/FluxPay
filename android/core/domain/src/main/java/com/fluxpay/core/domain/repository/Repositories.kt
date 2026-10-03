package com.fluxpay.core.domain.repository

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.Recipient
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionFilter
import com.fluxpay.core.domain.model.TransferReceipt
import com.fluxpay.core.domain.model.TransferRequest
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.model.UserPreferences
import kotlinx.coroutines.flow.Flow

interface AuthRepository {
    val isLoggedIn: Flow<Boolean>

    suspend fun login(email: String, password: String): NetworkResult<User>

    suspend fun register(
        fullName: String,
        email: String,
        phoneNumber: String,
        password: String,
        currency: String,
    ): NetworkResult<User>

    /** Revokes the refresh token on the server (best effort) and wipes all local data. */
    suspend fun logout(revokeRemotely: Boolean = true)

    suspend fun requestPasswordReset(email: String): NetworkResult<String>

    suspend fun confirmPasswordReset(uid: String, token: String, newPassword: String): NetworkResult<String>

    fun observeProfile(): Flow<User?>

    suspend fun refreshProfile(): NetworkResult<User>
}

/**
 * Offline-first: `observe*` streams always come from the local Room cache;
 * `refresh*` pulls from Django and writes into the cache, which re-emits.
 */
interface AccountRepository {
    fun observeAccounts(): Flow<List<Account>>

    suspend fun refreshAccounts(): NetworkResult<Unit>

    suspend fun lookupRecipient(accountNumber: String): NetworkResult<Recipient>
}

interface TransactionRepository {
    fun observeTransactions(filter: TransactionFilter = TransactionFilter()): Flow<List<Transaction>>

    fun observeTransaction(id: String): Flow<Transaction?>

    suspend fun refreshTransactions(): NetworkResult<Unit>

    suspend fun refreshTransaction(id: String): NetworkResult<Unit>
}

interface TransferRepository {
    suspend fun send(request: TransferRequest): NetworkResult<TransferReceipt>
}

interface PreferencesRepository {
    val preferences: Flow<UserPreferences>

    suspend fun setCurrency(currency: String)

    suspend fun setThemeMode(mode: ThemeMode)

    suspend fun setHideBalances(hide: Boolean)

    suspend fun clear()
}
