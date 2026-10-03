package com.fluxpay.core.database

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.fluxpay.core.database.dao.AccountDao
import com.fluxpay.core.database.dao.TransactionDao
import com.fluxpay.core.database.dao.UserDao
import com.fluxpay.core.database.entity.AccountEntity
import com.fluxpay.core.database.entity.TransactionEntity
import com.fluxpay.core.database.entity.UserEntity

@Database(
    entities = [UserEntity::class, AccountEntity::class, TransactionEntity::class],
    version = 1,
    exportSchema = true,
)
@TypeConverters(Converters::class)
abstract class FluxPayDatabase : RoomDatabase() {
    abstract fun userDao(): UserDao
    abstract fun accountDao(): AccountDao
    abstract fun transactionDao(): TransactionDao

    companion object {
        const val NAME = "fluxpay.db"
    }
}
