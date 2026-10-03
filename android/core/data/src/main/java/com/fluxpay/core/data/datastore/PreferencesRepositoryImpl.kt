package com.fluxpay.core.data.datastore

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import com.fluxpay.core.common.util.Constants
import com.fluxpay.core.data.di.SettingsDataStore
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.domain.model.UserPreferences
import com.fluxpay.core.domain.repository.PreferencesRepository
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map

/** Preferred currency, theme and "hide balances" flag, persisted with Preferences DataStore. */
@Singleton
class PreferencesRepositoryImpl @Inject constructor(
    @SettingsDataStore private val dataStore: DataStore<Preferences>,
) : PreferencesRepository {

    override val preferences: Flow<UserPreferences> = dataStore.data
        .catch { e -> if (e is IOException) emit(emptyPreferences()) else throw e }
        .map { prefs ->
            UserPreferences(
                currency = prefs[CURRENCY] ?: Constants.DEFAULT_CURRENCY,
                themeMode = prefs[THEME]?.let { name -> ThemeMode.entries.firstOrNull { it.name == name } }
                    ?: ThemeMode.SYSTEM,
                hideBalances = prefs[HIDE_BALANCES] ?: false,
            )
        }
        .distinctUntilChanged()

    override suspend fun setCurrency(currency: String) {
        dataStore.edit { it[CURRENCY] = currency }
    }

    override suspend fun setThemeMode(mode: ThemeMode) {
        dataStore.edit { it[THEME] = mode.name }
    }

    override suspend fun setHideBalances(hide: Boolean) {
        dataStore.edit { it[HIDE_BALANCES] = hide }
    }

    override suspend fun clear() {
        dataStore.edit { it.clear() }
    }

    private companion object {
        val CURRENCY = stringPreferencesKey("preferred_currency")
        val THEME = stringPreferencesKey("theme_mode")
        val HIDE_BALANCES = booleanPreferencesKey("hide_balances")
    }
}
