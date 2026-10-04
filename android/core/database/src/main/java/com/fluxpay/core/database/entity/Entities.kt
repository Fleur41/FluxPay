package com.fluxpay.core.database.entity

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import java.math.BigDecimal
import java.time.Instant

@Entity(tableName = "users")
data class UserEntity(
    @PrimaryKey val id: String,
    val email: String,
    @ColumnInfo(name = "full_name") val fullName: String,
    @ColumnInfo(name = "phone_number") val phoneNumber: String,
)

@Entity(tableName = "accounts", indices = [Index(value = ["account_number"], unique = true)])
data class AccountEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "account_number") val accountNumber: String,
    val name: String,
    val currency: String,
    val balance: BigDecimal,
    @ColumnInfo(name = "updated_at") val updatedAt: Instant,
)

@Entity(
    tableName = "transactions",
    indices = [Index(value = ["account_id", "created_at"]), Index(value = ["created_at"])],
)
data class TransactionEntity(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "account_id") val accountId: String,
    val type: String,
    val category: String,
    val status: String,
    val amount: BigDecimal,
    val currency: String,
    @ColumnInfo(name = "balance_after") val balanceAfter: BigDecimal,
    @ColumnInfo(name = "counterparty_name") val counterpartyName: String,
    @ColumnInfo(name = "counterparty_account") val counterpartyAccount: String,
    val description: String,
    val reference: String,
    @ColumnInfo(name = "created_at") val createdAt: Instant,
)

/** The budget planner's lines. Typed in by the user, so unlike the server caches it needs real migrations. */
@Entity(tableName = "budget_lines")
data class BudgetLineEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val label: String,
    val amount: BigDecimal,
    /** BudgetKind name: INCOME, NEEDS, WANTS or SAVINGS. */
    val kind: String,
    @ColumnInfo(name = "created_at") val createdAt: Instant,
)
