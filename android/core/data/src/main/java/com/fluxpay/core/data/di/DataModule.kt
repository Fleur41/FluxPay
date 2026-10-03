package com.fluxpay.core.data.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStoreFile
import com.fluxpay.core.common.auth.AuthTokenStore
import com.fluxpay.core.data.datastore.PreferencesRepositoryImpl
import com.fluxpay.core.data.datastore.SecureTokenStore
import com.fluxpay.core.data.repository.AccountRepositoryImpl
import com.fluxpay.core.data.repository.AuthRepositoryImpl
import com.fluxpay.core.data.repository.TransactionRepositoryImpl
import com.fluxpay.core.data.repository.TransferRepositoryImpl
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.domain.repository.PreferencesRepository
import com.fluxpay.core.domain.repository.TransactionRepository
import com.fluxpay.core.domain.repository.TransferRepository
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Qualifier
import javax.inject.Singleton

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class SessionDataStore

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class SettingsDataStore

@Module
@InstallIn(SingletonComponent::class)
abstract class DataModule {
    @Binds abstract fun bindTokenStore(impl: SecureTokenStore): AuthTokenStore
    @Binds abstract fun bindAuthRepository(impl: AuthRepositoryImpl): AuthRepository
    @Binds abstract fun bindAccountRepository(impl: AccountRepositoryImpl): AccountRepository
    @Binds abstract fun bindTransactionRepository(impl: TransactionRepositoryImpl): TransactionRepository
    @Binds abstract fun bindTransferRepository(impl: TransferRepositoryImpl): TransferRepository
    @Binds abstract fun bindPreferencesRepository(impl: PreferencesRepositoryImpl): PreferencesRepository
}

@Module
@InstallIn(SingletonComponent::class)
object DataStoreModule {
    // Only the application Context is used, so nothing here can leak an Activity.

    @Provides
    @Singleton
    @SessionDataStore
    fun provideSessionDataStore(@ApplicationContext context: Context): DataStore<Preferences> =
        PreferenceDataStoreFactory.create(produceFile = { context.preferencesDataStoreFile("fluxpay_session") })

    @Provides
    @Singleton
    @SettingsDataStore
    fun provideSettingsDataStore(@ApplicationContext context: Context): DataStore<Preferences> =
        PreferenceDataStoreFactory.create(produceFile = { context.preferencesDataStoreFile("fluxpay_settings") })
}
