package com.fluxpay.core.domain.usecase

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.BusinessBalance
import com.fluxpay.core.domain.model.PlatformConfig
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.model.UserPreferences
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.domain.repository.BusinessRepository
import com.fluxpay.core.domain.repository.ConfigRepository
import com.fluxpay.core.domain.repository.PreferencesRepository
import javax.inject.Inject
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map

/** Use cases shared by several features. Feature-specific ones live in each feature's `domain` package. */

class ObserveSessionUseCase @Inject constructor(private val authRepository: AuthRepository) {
    operator fun invoke(): Flow<Boolean> = authRepository.isLoggedIn.distinctUntilChanged()
}

class LogoutUseCase @Inject constructor(
    private val authRepository: AuthRepository,
    private val businessRepository: BusinessRepository,
) {
    suspend operator fun invoke(revokeRemotely: Boolean = true) {
        businessRepository.clearMine() // the next person to sign in must not see these businesses
        authRepository.logout(revokeRemotely)
    }
}

/** The user's businesses with their cashbook balances; null until loaded, empty for workers and personal users. */
class ObserveMyBusinessesUseCase @Inject constructor(private val businessRepository: BusinessRepository) {
    operator fun invoke(): Flow<List<BusinessBalance>?> = businessRepository.observeMyBusinesses()
}

/**
 * Whether to show the Business tab: only to people who run a business (owners, admins, finance, viewers).
 * Workers are paid by a business but aren't part of running it, so they don't get the tab.
 */
class ObserveCanSeeBusinessUseCase @Inject constructor(private val businessRepository: BusinessRepository) {
    operator fun invoke(): Flow<Boolean> =
        businessRepository.observeMyBusinesses().map { !it.isNullOrEmpty() }.distinctUntilChanged()
}

class RefreshMyBusinessesUseCase @Inject constructor(private val businessRepository: BusinessRepository) {
    suspend operator fun invoke(): NetworkResult<Unit> = businessRepository.refreshMine()
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

/** Business rules (currencies, limits, timeouts) from the server; null until first loaded. */
class ObservePlatformConfigUseCase @Inject constructor(private val configRepository: ConfigRepository) {
    operator fun invoke(): Flow<PlatformConfig?> = configRepository.config
}

class RefreshPlatformConfigUseCase @Inject constructor(private val configRepository: ConfigRepository) {
    suspend operator fun invoke(): NetworkResult<PlatformConfig> = configRepository.refresh()
}
