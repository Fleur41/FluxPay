package com.fluxpay.core.database

import androidx.room.AutoMigration
import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.fluxpay.core.database.dao.AccountDao
import com.fluxpay.core.database.dao.BudgetDao
import com.fluxpay.core.database.dao.TransactionDao
import com.fluxpay.core.database.dao.UserDao
import com.fluxpay.core.database.entity.AccountEntity
import com.fluxpay.core.database.entity.BudgetLineEntity
import com.fluxpay.core.database.entity.TransactionEntity
import com.fluxpay.core.database.entity.UserEntity

@Database(
    entities = [UserEntity::class, AccountEntity::class, TransactionEntity::class, BudgetLineEntity::class],
    version = 2,
    exportSchema = true,
    // Budget lines are user data, not a server cache: every schema change from here on needs a migration.
    autoMigrations = [AutoMigration(from = 1, to = 2)],
)
@TypeConverters(Converters::class)
abstract class FluxPayDatabase : RoomDatabase() {
    abstract fun userDao(): UserDao
    abstract fun accountDao(): AccountDao
    abstract fun transactionDao(): TransactionDao
    abstract fun budgetDao(): BudgetDao

    companion object {
        const val NAME = "fluxpay.db"
    }
}
