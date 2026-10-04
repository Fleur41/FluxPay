package com.fluxpay.feature.budget.domain

import com.fluxpay.core.domain.model.BudgetGuideline
import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import java.math.BigDecimal
import java.math.RoundingMode

/** How one spending group compares with the needs/wants/savings guideline. */
data class GuidelineCheck(
    val kind: BudgetKind,
    val planned: BigDecimal,
    /** Share of income, in whole percent; null without income. */
    val sharePercent: Int?,
    val targetPercent: Int,
    /** Needs and wants should stay at or under target; savings should reach it. */
    val isHealthy: Boolean,
)

data class BudgetSummary(
    val income: BigDecimal,
    val needs: BigDecimal,
    val wants: BigDecimal,
    val savings: BigDecimal,
    /** Everything planned to leave the income: needs + wants + savings. */
    val planned: BigDecimal,
    /** Income minus planned. Negative means the plan spends more than comes in. */
    val leftOver: BigDecimal,
    val savingsRatePercent: Int?,
    /** Empty when the guideline (from the server's platform settings) hasn't loaded. */
    val guideline: List<GuidelineCheck>,
    /** Money that actually left the wallet this month. */
    val spentThisMonth: BigDecimal,
    /** Planned needs + wants: what the month's spending is measured against. */
    val spendingPlan: BigDecimal,
) {
    val isOverPlanned: Boolean get() = leftOver.signum() < 0

    /** Spent this month against the spending plan, 0.0–1.0+; null when nothing is planned. */
    val spentFraction: Float? get() =
        if (spendingPlan.signum() > 0) spentThisMonth.divide(spendingPlan, 4, RoundingMode.HALF_UP).toFloat() else null
}

/** Pure arithmetic for the budget planner: no Android, no I/O, so it is fully unit-tested. */
object BudgetCalculator {

    /** `guideline` is the needs/wants/savings split staff set on the server (e.g. 50/30/20); null skips the check. */
    fun summarize(lines: List<BudgetLine>, spentThisMonth: BigDecimal, guideline: BudgetGuideline?): BudgetSummary {
        fun total(kind: BudgetKind) = lines.filter { it.kind == kind }.fold(BigDecimal.ZERO) { sum, line -> sum + line.amount }

        val income = total(BudgetKind.INCOME)
        val needs = total(BudgetKind.NEEDS)
        val wants = total(BudgetKind.WANTS)
        val savings = total(BudgetKind.SAVINGS)
        val planned = needs + wants + savings

        val targets = guideline?.let {
            listOf(BudgetKind.NEEDS to it.needsPercent, BudgetKind.WANTS to it.wantsPercent, BudgetKind.SAVINGS to it.savingsPercent)
        }.orEmpty()
        val checks = targets.map { (kind, target) ->
            val amount = when (kind) {
                BudgetKind.NEEDS -> needs
                BudgetKind.WANTS -> wants
                else -> savings
            }
            val share = percentOf(amount, income)
            GuidelineCheck(
                kind = kind,
                planned = amount,
                sharePercent = share,
                targetPercent = target,
                isHealthy = when {
                    share == null -> true
                    kind == BudgetKind.SAVINGS -> share >= target
                    else -> share <= target
                },
            )
        }

        return BudgetSummary(
            income = income,
            needs = needs,
            wants = wants,
            savings = savings,
            planned = planned,
            leftOver = income - planned,
            savingsRatePercent = percentOf(savings, income),
            guideline = checks,
            spentThisMonth = spentThisMonth,
            spendingPlan = needs + wants,
        )
    }

    private fun percentOf(part: BigDecimal, whole: BigDecimal): Int? =
        if (whole.signum() <= 0) null else part.multiply(BigDecimal(100)).divide(whole, 0, RoundingMode.HALF_UP).toInt()
}
