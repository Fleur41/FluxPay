package com.fluxpay.core.database.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Upsert
import com.fluxpay.core.database.entity.AccountEntity
import com.fluxpay.core.database.entity.BudgetLineEntity
import com.fluxpay.core.database.entity.TransactionEntity
import com.fluxpay.core.database.entity.UserEntity
import java.math.BigDecimal
import kotlinx.coroutines.flow.Flow

@Dao
interface UserDao {
    @Query("SELECT * FROM users LIMIT 1")
    fun observeUser(): Flow<UserEntity?>

    @Upsert
    suspend fun upsert(user: UserEntity)

    @Query("DELETE FROM users")
    suspend fun clear()
}

@Dao
abstract class AccountDao {
    @Query("SELECT * FROM accounts ORDER BY name")
    abstract fun observeAccounts(): Flow<List<AccountEntity>>

    @Upsert
    abstract suspend fun upsertAll(accounts: List<AccountEntity>)

    @Query("DELETE FROM accounts WHERE id NOT IN (:keepIds)")
    abstract suspend fun deleteAllExcept(keepIds: List<String>)

    /** Replaces the cache atomically so the UI never sees a half-written list. */
    @Transaction
    open suspend fun replaceAll(accounts: List<AccountEntity>) {
        deleteAllExcept(accounts.map { it.id })
        upsertAll(accounts)
    }
}

@Dao
abstract class TransactionDao {
    /** Every filter is optional: passing null disables that condition. */
    @Query(
        """
        SELECT * FROM transactions
        WHERE (:accountId IS NULL OR account_id = :accountId)
          AND (:type IS NULL OR type = :type)
          AND (:query IS NULL
               OR description LIKE '%' || :query || '%'
               OR counterparty_name LIKE '%' || :query || '%'
               OR counterparty_account LIKE '%' || :query || '%'
               OR reference LIKE '%' || :query || '%')
          AND (:fromMillis IS NULL OR created_at >= :fromMillis)
          AND (:toMillis IS NULL OR created_at <= :toMillis)
        ORDER BY created_at DESC
        LIMIT :limit
        """,
    )
    abstract fun observeTransactions(
        accountId: String?,
        type: String?,
        query: String?,
        fromMillis: Long?,
        toMillis: Long?,
        limit: Int,
    ): Flow<List<TransactionEntity>>

    @Query("SELECT * FROM transactions WHERE id = :id")
    abstract fun observeTransaction(id: String): Flow<TransactionEntity?>

    /** Amounts of completed money-out lines in [fromMillis, toMillis). Summed by the caller: amounts are TEXT. */
    @Query(
        """
        SELECT amount FROM transactions
        WHERE type = 'DEBIT' AND status = 'COMPLETED' AND created_at >= :fromMillis AND created_at < :toMillis
        """,
    )
    abstract fun observeDebitAmounts(fromMillis: Long, toMillis: Long): Flow<List<BigDecimal>>

    @Upsert
    abstract suspend fun upsertAll(transactions: List<TransactionEntity>)

    @Upsert
    abstract suspend fun upsert(transaction: TransactionEntity)

    @Query("DELETE FROM transactions")
    abstract suspend fun clear()

    @Transaction
    open suspend fun replaceAll(transactions: List<TransactionEntity>) {
        clear()
        upsertAll(transactions)
    }
}

@Dao
interface BudgetDao {
    @Query("SELECT * FROM budget_lines ORDER BY created_at, id")
    fun observeLines(): Flow<List<BudgetLineEntity>>

    @Upsert
    suspend fun upsert(line: BudgetLineEntity)

    @Query("SELECT * FROM budget_lines WHERE id = :id")
    suspend fun find(id: Long): BudgetLineEntity?

    @Query("DELETE FROM budget_lines WHERE id = :id")
    suspend fun delete(id: Long)
}
