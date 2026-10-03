package com.fluxpay.core.data.datastore

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import com.fluxpay.core.common.auth.AuthTokenStore
import com.fluxpay.core.common.auth.AuthTokens
import com.fluxpay.core.data.di.SessionDataStore
import com.fluxpay.core.data.security.KeystoreCipher
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.runBlocking

/**
 * JWTs are encrypted with a Keystore AES key and persisted in a dedicated DataStore file.
 * An in-memory copy avoids disk reads on every HTTP request.
 */
@Singleton
class SecureTokenStore @Inject constructor(
    @SessionDataStore private val dataStore: DataStore<Preferences>,
    private val cipher: KeystoreCipher,
) : AuthTokenStore {

    @Volatile private var cached: AuthTokens? = null
    @Volatile private var loaded = false

    private val safeData: Flow<Preferences> = dataStore.data.catch { e ->
        if (e is IOException) emit(emptyPreferences()) else throw e
    }

    override val isLoggedIn: Flow<Boolean> = safeData.map { it[REFRESH_KEY] != null }

    override fun accessToken(): String? = load()?.access

    override fun refreshToken(): String? = load()?.refresh

    override suspend fun save(tokens: AuthTokens) {
        dataStore.edit {
            it[ACCESS_KEY] = cipher.encrypt(tokens.access)
            it[REFRESH_KEY] = cipher.encrypt(tokens.refresh)
        }
        cached = tokens
        loaded = true
    }

    override suspend fun clear() {
        dataStore.edit { it.clear() }
        cached = null
        loaded = true
    }

    /** Only ever called from OkHttp worker threads, so blocking once on first use is fine. */
    private fun load(): AuthTokens? {
        if (!loaded) {
            synchronized(this) {
                if (!loaded) {
                    cached = runBlocking { readFromDisk() }
                    loaded = true
                }
            }
        }
        return cached
    }

    private suspend fun readFromDisk(): AuthTokens? {
        val prefs = safeData.first()
        val access = prefs[ACCESS_KEY]?.let(cipher::decrypt)
        val refresh = prefs[REFRESH_KEY]?.let(cipher::decrypt)
        return if (access != null && refresh != null) AuthTokens(access, refresh) else null
    }

    private companion object {
        val ACCESS_KEY = stringPreferencesKey("access_token")
        val REFRESH_KEY = stringPreferencesKey("refresh_token")
    }
}
