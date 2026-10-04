package com.fluxpay.feature.transactions.domain.model

import com.fluxpay.core.domain.model.StatementPeriod
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.time.temporal.TemporalAdjusters

/** The periods offered in the download sheet. Each ends today at the latest. */
enum class StatementRange(val label: String) {
    THIS_MONTH("This month"),
    LAST_MONTH("Last month"),
    LAST_3_MONTHS("Last 3 months"),
    THIS_YEAR("This year");

    fun period(today: LocalDate): StatementPeriod = when (this) {
        THIS_MONTH -> StatementPeriod(today.withDayOfMonth(1), today)
        LAST_MONTH -> today.minusMonths(1).let { month ->
            StatementPeriod(month.withDayOfMonth(1), month.with(TemporalAdjusters.lastDayOfMonth()))
        }
        // Two full months before this one, plus this month so far.
        LAST_3_MONTHS -> StatementPeriod(today.minusMonths(2).withDayOfMonth(1), today)
        THIS_YEAR -> StatementPeriod(today.withDayOfYear(1), today)
    }

    companion object {
        /** The presets whose period fits within the server's longest allowed statement (both ends included). */
        fun allowed(today: LocalDate, maxDays: Int): List<StatementRange> = entries.filter { range ->
            val period = range.period(today)
            ChronoUnit.DAYS.between(period.from, period.to) < maxDays
        }
    }
}
