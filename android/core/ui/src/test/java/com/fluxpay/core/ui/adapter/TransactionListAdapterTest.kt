package com.fluxpay.core.ui.adapter

import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionCategory
import com.fluxpay.core.domain.model.TransactionStatus
import com.fluxpay.core.domain.model.TransactionType
import java.math.BigDecimal
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TransactionListAdapterTest {

    private fun tx(id: String, at: String) = Transaction(
        id = id,
        accountId = "a",
        type = TransactionType.DEBIT,
        category = TransactionCategory.TRANSFER_OUT,
        status = TransactionStatus.COMPLETED,
        amount = BigDecimal("10.00"),
        currency = "KES",
        balanceAfter = BigDecimal("90.00"),
        counterpartyName = "Bob",
        counterpartyAccount = "1234567890",
        description = "",
        reference = "FP1",
        createdAt = Instant.parse(at),
    )

    @Test
    fun `groups by day newest first with headers`() {
        val items = TransactionListAdapter.adapt(
            listOf(tx("1", "2026-10-01T09:00:00Z"), tx("2", "2026-10-03T08:00:00Z"), tx("3", "2026-10-03T12:00:00Z")),
            zone = ZoneOffset.UTC,
            today = LocalDate.parse("2026-10-03"),
        )
        assertEquals(listOf("header-2026-10-03", "3", "2", "header-2026-10-01", "1"), items.map { it.key })
        assertEquals("Today", (items.first() as TransactionListItem.Header).label)
        assertTrue(items.last() is TransactionListItem.Row)
    }
}
