package com.fluxpay.core.data.repository

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.common.result.map
import com.fluxpay.core.data.di.ConfigDataStore
import com.fluxpay.core.domain.model.BudgetGuideline
import com.fluxpay.core.domain.model.CurrencyRule
import com.fluxpay.core.domain.model.PlatformConfig
import com.fluxpay.core.domain.repository.ConfigRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import com.fluxpay.core.network.dto.PlatformConfigDto
import com.squareup.moshi.Moshi
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

/**
 * The last good copy of GET /api/v1/config/ is kept in its own DataStore, so rules are available offline
 * and at start-up. It is not personal data, so sign-out does not clear it.
 */
@Singleton
class ConfigRepositoryImpl @Inject constructor(
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    moshi: Moshi,
    @ConfigDataStore private val dataStore: DataStore<Preferences>,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : ConfigRepository {

    private val adapter = moshi.adapter(PlatformConfigDto::class.java)

    override val config: Flow<PlatformConfig?> = dataStore.data
        .catch { e -> if (e is IOException) emit(emptyPreferences()) else throw e }
        .map { prefs -> prefs[CACHED]?.let { json -> runCatching { adapter.fromJson(json)?.toDomain() }.getOrNull() } }
        .distinctUntilChanged()

    override suspend fun refresh(): NetworkResult<PlatformConfig> = withContext(io) {
        val result = apiCaller { api.config() }
        if (result is NetworkResult.Success) {
            runCatching { result.data.toDomain() }.onSuccess { dataStore.edit { it[CACHED] = adapter.toJson(result.data) } }
        }
        result.map { it.toDomain() }
    }

    private fun PlatformConfigDto.toDomain() = PlatformConfig(
        currencies = currencies.map { CurrencyRule(it.code, it.name, it.minTransfer, it.maxTransfer) },
        defaultCurrency = defaultCurrency,
        statementMaxDays = statementMaxDays,
        sessionTimeoutMinutes = sessionTimeoutMinutes,
        budgetGuideline = BudgetGuideline(
            needsPercent = budgetGuideline.getValue("needs"),
            wantsPercent = budgetGuideline.getValue("wants"),
            savingsPercent = budgetGuideline.getValue("savings"),
        ),
    )

    private companion object {
        val CACHED = stringPreferencesKey("platform_config_json")
    }
}
