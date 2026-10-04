package com.fluxpay.feature.budget.domain.usecase

import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.core.domain.repository.AccountRepository
import com.fluxpay.core.domain.repository.BudgetRepository
import com.fluxpay.core.domain.repository.ConfigRepository
import com.fluxpay.feature.budget.domain.BudgetCalculator
import com.fluxpay.feature.budget.domain.BudgetSummary
import java.math.BigDecimal
import java.time.Clock
import java.time.LocalDate
import java.time.ZoneId
import javax.inject.Inject
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine

data class BudgetSnapshot(
    val lines: List<BudgetLine>,
    val summary: BudgetSummary,
    /** The user's wallet currency, or the platform default; null until either is known. */
    val currency: String?,
)

class ObserveBudgetUseCase @Inject constructor(
    private val budgetRepository: BudgetRepository,
    private val accountRepository: AccountRepository,
    private val configRepository: ConfigRepository,
) {
    /** Lines, their summary and this calendar month's spending, recomputed whenever any of them change. */
    operator fun invoke(clock: Clock = Clock.systemDefaultZone()): Flow<BudgetSnapshot> {
        val zone: ZoneId = clock.zone
        val monthStart = LocalDate.now(clock).withDayOfMonth(1)
        val from = monthStart.atStartOfDay(zone).toInstant()
        val to = monthStart.plusMonths(1).atStartOfDay(zone).toInstant()
        return combine(
            budgetRepository.observeLines(),
            budgetRepository.observeSpending(from, to),
            accountRepository.observeAccounts(),
            configRepository.config,
        ) { lines, spent, accounts, config ->
            BudgetSnapshot(
                lines = lines,
                summary = BudgetCalculator.summarize(lines, spent, config?.budgetGuideline),
                currency = accounts.firstOrNull()?.currency ?: config?.defaultCurrency,
            )
        }
    }
}

sealed interface SaveResult {
    data object Saved : SaveResult
    data class Invalid(val labelError: String? = null, val amountError: String? = null) : SaveResult
}

class SaveBudgetLineUseCase @Inject constructor(private val repository: BudgetRepository) {
    suspend operator fun invoke(id: Long, label: String, amount: BigDecimal?, kind: BudgetKind): SaveResult {
        val trimmed = label.trim()
        val labelError = when {
            trimmed.isEmpty() -> "Give this line a name"
            trimmed.length > MAX_LABEL -> "Keep it under $MAX_LABEL characters"
            else -> null
        }
        val amountError = when {
            amount == null -> "Enter an amount, e.g. 12,500"
            amount.signum() <= 0 -> "The amount must be more than zero"
            else -> null
        }
        if (labelError != null || amountError != null) return SaveResult.Invalid(labelError, amountError)
        repository.save(BudgetLine(id = id, label = trimmed, amount = amount!!, kind = kind))
        return SaveResult.Saved
    }

    private companion object {
        const val MAX_LABEL = 40
    }
}

class DeleteBudgetLineUseCase @Inject constructor(private val repository: BudgetRepository) {
    suspend operator fun invoke(id: Long) = repository.delete(id)
}
