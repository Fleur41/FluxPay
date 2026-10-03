package com.fluxpay.core.data.mapper

import com.fluxpay.core.database.entity.AccountEntity
import com.fluxpay.core.database.entity.TransactionEntity
import com.fluxpay.core.database.entity.UserEntity
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.Recipient
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionCategory
import com.fluxpay.core.domain.model.TransactionStatus
import com.fluxpay.core.domain.model.TransactionType
import com.fluxpay.core.domain.model.TransferReceipt
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.network.dto.AccountDto
import com.fluxpay.core.network.dto.RecipientDto
import com.fluxpay.core.network.dto.TransactionDto
import com.fluxpay.core.network.dto.TransferResponseDto
import com.fluxpay.core.network.dto.UserDto

/*
 * Adapter pattern: these functions adapt the shapes of other layers to each other.
 *   Django DTO  ──toEntity()──▶  Room entity  ──toDomain()──▶  domain model
 * The domain never sees Moshi/Room annotations, and a backend field rename only
 * touches the DTO and this file.
 */

fun UserDto.toEntity() = UserEntity(id = id, email = email, fullName = fullName, phoneNumber = phoneNumber)

fun UserEntity.toDomain() = User(id = id, email = email, fullName = fullName, phoneNumber = phoneNumber)

fun AccountDto.toEntity() = AccountEntity(
    id = id,
    accountNumber = accountNumber,
    name = name,
    currency = currency,
    balance = balance,
    updatedAt = updatedAt,
)

fun AccountEntity.toDomain() = Account(
    id = id,
    accountNumber = accountNumber,
    name = name,
    currency = currency,
    balance = balance,
    updatedAt = updatedAt,
)

fun TransactionDto.toEntity() = TransactionEntity(
    id = id,
    accountId = accountId,
    type = type,
    category = category,
    status = status,
    amount = amount,
    currency = currency,
    balanceAfter = balanceAfter,
    counterpartyName = counterpartyName,
    counterpartyAccount = counterpartyAccount,
    description = description,
    reference = reference,
    createdAt = createdAt,
)

fun TransactionEntity.toDomain() = Transaction(
    id = id,
    accountId = accountId,
    type = enumOrDefault(type, TransactionType.DEBIT),
    category = enumOrDefault(category, TransactionCategory.UNKNOWN),
    status = enumOrDefault(status, TransactionStatus.UNKNOWN),
    amount = amount,
    currency = currency,
    balanceAfter = balanceAfter,
    counterpartyName = counterpartyName,
    counterpartyAccount = counterpartyAccount,
    description = description,
    reference = reference,
    createdAt = createdAt,
)

fun RecipientDto.toDomain() = Recipient(accountNumber = accountNumber, currency = currency, holderName = holderName)

fun TransferResponseDto.toDomain() = TransferReceipt(
    transferId = transfer.id,
    reference = transfer.reference,
    amount = transfer.amount,
    currency = transfer.currency,
    recipientName = transfer.recipientName,
    destinationAccountNumber = transfer.destinationAccountNumber,
    note = transfer.note,
    createdAt = transfer.createdAt,
    transaction = transaction.toEntity().toDomain(),
)

/** Unknown values from a newer backend shouldn't crash older app versions. */
private inline fun <reified E : Enum<E>> enumOrDefault(value: String, default: E): E =
    enumValues<E>().firstOrNull { it.name == value } ?: default
