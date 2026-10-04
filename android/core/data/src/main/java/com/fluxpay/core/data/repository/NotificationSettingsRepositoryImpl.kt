package com.fluxpay.core.data.repository

import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.result.map
import com.fluxpay.core.domain.model.NotificationSettings
import com.fluxpay.core.domain.repository.NotificationSettingsRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.dto.NotificationSettingsDto
import com.fluxpay.core.network.dto.NotificationSettingsPatchDto
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext

@Singleton
class NotificationSettingsRepositoryImpl @Inject constructor(
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : NotificationSettingsRepository {

    override suspend fun get(): NetworkResult<NotificationSettings> = withContext(io) {
        apiCaller { api.notificationSettings() }.map { it.toDomain() }
    }

    override suspend fun update(emailEnabled: Boolean?, smsEnabled: Boolean?): NetworkResult<NotificationSettings> =
        withContext(io) {
            apiCaller { api.updateNotificationSettings(NotificationSettingsPatchDto(emailEnabled, smsEnabled)) }
                .map { it.toDomain() }
        }

    private fun NotificationSettingsDto.toDomain() = NotificationSettings(emailEnabled = emailEnabled, smsEnabled = smsEnabled)
}
