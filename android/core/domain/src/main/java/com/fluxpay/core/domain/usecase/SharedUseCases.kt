package com.fluxpay.core.domain.usecase

import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.model.UserPreferences
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.domain.repository.PreferencesRepository
import javax.inject.Inject
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged

/** Use cases shared by several features. Feature-specific ones live in each feature's `domain` package. */

class ObserveSessionUseCase @Inject constructor(private val authRepository: AuthRepository) {
    operator fun invoke(): Flow<Boolean> = authRepository.isLoggedIn.distinctUntilChanged()
}

class LogoutUseCase @Inject constructor(private val authRepository: AuthRepository) {
    suspend operator fun invoke(revokeRemotely: Boolean = true) = authRepository.logout(revokeRemotely)
}

class ObservePreferencesUseCase @Inject constructor(private val preferencesRepository: PreferencesRepository) {
    operator fun invoke(): Flow<UserPreferences> = preferencesRepository.preferences
}

class ObserveAccountsUseCase @Inject constructor(private val accountRepository: AccountRepository) {
    operator fun invoke(): Flow<List<Account>> = accountRepository.observeAccounts()
}

class ObserveProfileUseCase @Inject constructor(private val authRepository: AuthRepository) {
    operator fun invoke(): Flow<User?> = authRepository.observeProfile()
}
