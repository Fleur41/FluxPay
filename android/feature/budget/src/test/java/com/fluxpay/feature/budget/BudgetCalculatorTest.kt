package com.fluxpay.feature.budget

import com.fluxpay.core.domain.model.BudgetGuideline
import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.feature.budget.domain.BudgetCalculator
import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BudgetCalculatorTest {

    /** As staff might set it in the backend's platform settings. */
    private val guide = BudgetGuideline(needsPercent = 50, wantsPercent = 30, savingsPercent = 20)

    private fun line(kind: BudgetKind, amount: String, label: String = kind.label) =
        BudgetLine(label = label, amount = BigDecimal(amount), kind = kind)

    private val salaryPlan = listOf(
        line(BudgetKind.INCOME, "60000.00", "Salary"),
        line(BudgetKind.INCOME, "10000.00", "Side hustle"),
        line(BudgetKind.NEEDS, "25000.00", "Rent"),
        line(BudgetKind.NEEDS, "10000.00", "Food"),
        line(BudgetKind.WANTS, "14000.00", "Eating out"),
        line(BudgetKind.SAVINGS, "14000.00", "Chama"),
    )

    @Test
    fun `totals, left over and savings rate`() {
        val summary = BudgetCalculator.summarize(salaryPlan, BigDecimal("12000.00"), guide)
        assertEquals(BigDecimal("70000.00"), summary.income)
        assertEquals(BigDecimal("35000.00"), summary.needs)
        assertEquals(BigDecimal("63000.00"), summary.planned)
        assertEquals(BigDecimal("7000.00"), summary.leftOver)
        assertEquals(20, summary.savingsRatePercent)
        assertFalse(summary.isOverPlanned)
    }

    @Test
    fun `50-30-20 check marks each group`() {
        val checks = BudgetCalculator.summarize(salaryPlan, BigDecimal.ZERO, guide).guideline.associateBy { it.kind }
        assertEquals(50, checks.getValue(BudgetKind.NEEDS).sharePercent)
        assertTrue(checks.getValue(BudgetKind.NEEDS).isHealthy) // exactly on target is fine
        assertEquals(20, checks.getValue(BudgetKind.WANTS).sharePercent)
        assertTrue(checks.getValue(BudgetKind.WANTS).isHealthy)
        assertEquals(20, checks.getValue(BudgetKind.SAVINGS).sharePercent)
        assertTrue(checks.getValue(BudgetKind.SAVINGS).isHealthy)

        val heavyRent = salaryPlan + line(BudgetKind.NEEDS, "5000.00", "Water")
        val needs = BudgetCalculator.summarize(heavyRent, BigDecimal.ZERO, guide).guideline.first { it.kind == BudgetKind.NEEDS }
        assertEquals(57, needs.sharePercent)
        assertFalse(needs.isHealthy)
    }

    @Test
    fun `saving less than 20 percent is flagged`() {
        val plan = listOf(line(BudgetKind.INCOME, "50000"), line(BudgetKind.SAVINGS, "5000"))
        val savings = BudgetCalculator.summarize(plan, BigDecimal.ZERO, guide).guideline.first { it.kind == BudgetKind.SAVINGS }
        assertEquals(10, savings.sharePercent)
        assertFalse(savings.isHealthy)
    }

    @Test
    fun `spending more than you earn is over planned`() {
        val plan = listOf(line(BudgetKind.INCOME, "20000"), line(BudgetKind.NEEDS, "25000"))
        val summary = BudgetCalculator.summarize(plan, BigDecimal.ZERO, guide)
        assertEquals(BigDecimal("-5000"), summary.leftOver)
        assertTrue(summary.isOverPlanned)
    }

    @Test
    fun `month spending is measured against needs plus wants`() {
        val summary = BudgetCalculator.summarize(salaryPlan, BigDecimal("24500.00"), guide)
        assertEquals(BigDecimal("49000.00"), summary.spendingPlan)
        assertEquals(0.5f, summary.spentFraction!!, 0.0001f)
    }

    @Test
    fun `no income means no percentages and nothing flagged`() {
        val summary = BudgetCalculator.summarize(listOf(line(BudgetKind.WANTS, "3000")), BigDecimal.ZERO, guide)
        assertNull(summary.savingsRatePercent)
        assertTrue(summary.guideline.all { it.sharePercent == null && it.isHealthy })
    }

    @Test
    fun `empty budget`() {
        val summary = BudgetCalculator.summarize(emptyList(), BigDecimal("150.00"), guide)
        assertEquals(BigDecimal.ZERO, summary.leftOver)
        assertNull(summary.spentFraction)
        assertEquals(BigDecimal("150.00"), summary.spentThisMonth)
    }

    @Test
    fun `the guideline is whatever staff configured`() {
        val strict = BudgetGuideline(needsPercent = 40, wantsPercent = 20, savingsPercent = 40)
        val checks = BudgetCalculator.summarize(salaryPlan, BigDecimal.ZERO, strict).guideline.associateBy { it.kind }
        assertEquals(40, checks.getValue(BudgetKind.NEEDS).targetPercent)
        assertFalse(checks.getValue(BudgetKind.NEEDS).isHealthy) // 50% of income against a 40% target
        assertFalse(checks.getValue(BudgetKind.SAVINGS).isHealthy) // 20% saved against a 40% target
    }

    @Test
    fun `no guideline loaded means no check, totals still work`() {
        val summary = BudgetCalculator.summarize(salaryPlan, BigDecimal.ZERO, guideline = null)
        assertTrue(summary.guideline.isEmpty())
        assertEquals(BigDecimal("7000.00"), summary.leftOver)
    }
}
