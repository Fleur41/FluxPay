package com.fluxpay.core.data.repository

import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.database.dao.BudgetDao
import com.fluxpay.core.database.dao.TransactionDao
import com.fluxpay.core.database.entity.BudgetLineEntity
import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.core.domain.repository.BudgetRepository
import java.math.BigDecimal
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

/** Local only. Lives in the Room database, so sign-out (which clears all tables) wipes it too. */
@Singleton
class BudgetRepositoryImpl @Inject constructor(
    private val budgetDao: BudgetDao,
    private val transactionDao: TransactionDao,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : BudgetRepository {

    override fun observeLines(): Flow<List<BudgetLine>> = budgetDao.observeLines().map { lines ->
        lines.map { BudgetLine(id = it.id, label = it.label, amount = it.amount, kind = it.kind.toKind()) }
    }

    override suspend fun save(line: BudgetLine) = withContext(io) {
        val createdAt = budgetDao.find(line.id)?.createdAt ?: Instant.now() // keep a line's place when edited
        budgetDao.upsert(
            BudgetLineEntity(
                id = line.id,
                label = line.label.trim(),
                amount = line.amount,
                kind = line.kind.name,
                createdAt = createdAt,
            ),
        )
    }

    override suspend fun delete(id: Long) = withContext(io) { budgetDao.delete(id) }

    override fun observeSpending(from: Instant, to: Instant): Flow<BigDecimal> =
        transactionDao.observeDebitAmounts(from.toEpochMilli(), to.toEpochMilli())
            .map { amounts -> amounts.fold(BigDecimal.ZERO, BigDecimal::add) }

    private fun String.toKind() = BudgetKind.entries.firstOrNull { it.name == this } ?: BudgetKind.NEEDS
}
