package com.fluxpay.feature.transactions

import com.fluxpay.core.domain.model.StatementPeriod
import com.fluxpay.feature.transactions.domain.model.StatementRange
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import org.junit.Assert.assertEquals
import org.junit.Test

class StatementRangeTest {

    private val today = LocalDate.of(2026, 10, 3)

    @Test
    fun `this month runs from the 1st to today`() {
        assertEquals(StatementPeriod(LocalDate.of(2026, 10, 1), today), StatementRange.THIS_MONTH.period(today))
    }

    @Test
    fun `last month is the whole previous month`() {
        assertEquals(
            StatementPeriod(LocalDate.of(2026, 9, 1), LocalDate.of(2026, 9, 30)),
            StatementRange.LAST_MONTH.period(today),
        )
        // Across a year boundary and into a leap-year February.
        assertEquals(
            StatementPeriod(LocalDate.of(2027, 12, 1), LocalDate.of(2027, 12, 31)),
            StatementRange.LAST_MONTH.period(LocalDate.of(2028, 1, 15)),
        )
        assertEquals(
            StatementPeriod(LocalDate.of(2028, 2, 1), LocalDate.of(2028, 2, 29)),
            StatementRange.LAST_MONTH.period(LocalDate.of(2028, 3, 31)),
        )
    }

    @Test
    fun `last 3 months is two full months plus this one`() {
        assertEquals(StatementPeriod(LocalDate.of(2026, 8, 1), today), StatementRange.LAST_3_MONTHS.period(today))
    }

    @Test
    fun `this year starts on 1 January and stays within the server's 366-day limit`() {
        val period = StatementRange.THIS_YEAR.period(LocalDate.of(2028, 12, 31))
        assertEquals(LocalDate.of(2028, 1, 1), period.from)
        assertEquals(365L, ChronoUnit.DAYS.between(period.from, period.to)) // 366 days inclusive
    }

    @Test
    fun `only presets within the server's maximum are offered`() {
        assertEquals(StatementRange.entries, StatementRange.allowed(today, maxDays = 366))
        assertEquals(listOf(StatementRange.THIS_MONTH, StatementRange.LAST_MONTH), StatementRange.allowed(today, maxDays = 31))
        assertEquals(listOf(StatementRange.THIS_MONTH), StatementRange.allowed(today, maxDays = 7))
    }
}
