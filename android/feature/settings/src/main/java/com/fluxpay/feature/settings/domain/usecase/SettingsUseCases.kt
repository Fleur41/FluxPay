package com.fluxpay.feature.settings.domain.usecase

import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.repository.PreferencesRepository
import javax.inject.Inject

/** All writes to the DataStore-backed preferences go through here. */
class UpdatePreferencesUseCase @Inject constructor(private val repository: PreferencesRepository) {
    suspend fun currency(code: String) = repository.setCurrency(code)
    suspend fun theme(mode: ThemeMode) = repository.setThemeMode(mode)
    suspend fun hideBalances(hide: Boolean) = repository.setHideBalances(hide)
}
