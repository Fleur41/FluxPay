package com.fluxpay.core.database.di

import android.content.Context
import androidx.room.Room
import com.fluxpay.core.database.FluxPayDatabase
import com.fluxpay.core.database.dao.AccountDao
import com.fluxpay.core.database.dao.TransactionDao
import com.fluxpay.core.database.dao.UserDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): FluxPayDatabase =
        Room.databaseBuilder(context, FluxPayDatabase::class.java, FluxPayDatabase.NAME)
            // The DB is only a cache of server data, so wiping it on schema change is safe.
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideUserDao(db: FluxPayDatabase): UserDao = db.userDao()

    @Provides
    fun provideAccountDao(db: FluxPayDatabase): AccountDao = db.accountDao()

    @Provides
    fun provideTransactionDao(db: FluxPayDatabase): TransactionDao = db.transactionDao()
}
