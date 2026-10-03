package com.fluxpay.core.domain.model

import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TransferRequestTest {

    private fun validBuilder() = TransferRequest.builder()
        .from("acc-1")
        .to(" 1234567890 ")
        .amount(BigDecimal("250.00"))
        .note("  Lunch  ")

    @Test
    fun `builds a trimmed request and generates an idempotency key`() {
        val request = validBuilder().build()
        assertEquals("1234567890", request.destinationAccountNumber)
        assertEquals("Lunch", request.note)
        assertTrue(request.idempotencyKey.isNotBlank())
    }

    @Test
    fun `keeps a provided idempotency key for safe retries`() {
        val request = validBuilder().idempotencyKey("fixed-key-123").build()
        assertEquals("fixed-key-123", request.idempotencyKey)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `rejects zero amount`() {
        validBuilder().amount(BigDecimal.ZERO).build()
    }

    @Test(expected = IllegalArgumentException::class)
    fun `rejects more than two decimals`() {
        validBuilder().amount(BigDecimal("1.001")).build()
    }

    @Test(expected = IllegalArgumentException::class)
    fun `rejects malformed account number`() {
        validBuilder().to("12345").build()
    }
}
