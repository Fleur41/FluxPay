package com.fluxpay.feature.settings.domain.usecase

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.NotificationSettings
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.repository.NotificationSettingsRepository
import com.fluxpay.core.domain.repository.PreferencesRepository
import javax.inject.Inject

/** All writes to the DataStore-backed preferences go through here. */
class UpdatePreferencesUseCase @Inject constructor(private val repository: PreferencesRepository) {
    suspend fun currency(code: String) = repository.setCurrency(code)
    suspend fun theme(mode: ThemeMode) = repository.setThemeMode(mode)
    suspend fun hideBalances(hide: Boolean) = repository.setHideBalances(hide)
}

/** Transaction alert channels live on the server, so they follow the user to any phone. */
class NotificationSettingsUseCase @Inject constructor(private val repository: NotificationSettingsRepository) {
    suspend fun load(): NetworkResult<NotificationSettings> = repository.get()
    suspend fun setEmail(enabled: Boolean) = repository.update(emailEnabled = enabled)
    suspend fun setSms(enabled: Boolean) = repository.update(smsEnabled = enabled)
}
