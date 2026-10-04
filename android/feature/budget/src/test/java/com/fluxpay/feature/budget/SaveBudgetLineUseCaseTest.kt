package com.fluxpay.feature.budget

import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.core.domain.repository.BudgetRepository
import com.fluxpay.feature.budget.domain.usecase.SaveBudgetLineUseCase
import com.fluxpay.feature.budget.domain.usecase.SaveResult
import java.math.BigDecimal
import java.time.Instant
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SaveBudgetLineUseCaseTest {

    private class FakeRepository : BudgetRepository {
        val saved = mutableListOf<BudgetLine>()
        override fun observeLines(): Flow<List<BudgetLine>> = flowOf(saved)
        override suspend fun save(line: BudgetLine) { saved += line }
        override suspend fun delete(id: Long) { saved.removeAll { it.id == id } }
        override fun observeSpending(from: Instant, to: Instant): Flow<BigDecimal> = flowOf(BigDecimal.ZERO)
    }

    private val repository = FakeRepository()
    private val save = SaveBudgetLineUseCase(repository)

    @Test
    fun `saves a trimmed line`() = runTest {
        val result = save(0, "  Rent ", BigDecimal("25000.00"), BudgetKind.NEEDS)
        assertEquals(SaveResult.Saved, result)
        assertEquals("Rent", repository.saved.single().label)
    }

    @Test
    fun `rejects missing name and bad amounts without saving`() = runTest {
        val blank = save(0, "  ", BigDecimal("10"), BudgetKind.NEEDS) as SaveResult.Invalid
        assertEquals("Give this line a name", blank.labelError)

        val noAmount = save(0, "Food", null, BudgetKind.NEEDS) as SaveResult.Invalid
        assertTrue(noAmount.amountError!!.startsWith("Enter an amount"))

        val zero = save(0, "Food", BigDecimal.ZERO, BudgetKind.NEEDS) as SaveResult.Invalid
        assertEquals("The amount must be more than zero", zero.amountError)

        val long = save(0, "x".repeat(41), BigDecimal("10"), BudgetKind.NEEDS) as SaveResult.Invalid
        assertEquals("Keep it under 40 characters", long.labelError)

        assertTrue(repository.saved.isEmpty())
    }
}
