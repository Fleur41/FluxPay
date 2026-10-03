package com.fluxpay.feature.transfer

import com.fluxpay.core.domain.model.Account
import com.fluxpay.feature.transfer.domain.usecase.ValidateTransferUseCase
import java.math.BigDecimal
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ValidateTransferUseCaseTest {

    private val validate = ValidateTransferUseCase()
    private val wallet = Account("acc-1", "1111111111", "Main Wallet", "KES", BigDecimal("500.00"), Instant.EPOCH)

    @Test
    fun `valid form returns parsed amount`() {
        val result = validate(wallet, "2222222222", "250.5", "Lunch")
        assertTrue(result.errors.isValid)
        assertEquals(BigDecimal("250.50"), result.amount)
    }

    @Test
    fun `insufficient funds is caught before calling the server`() {
        val result = validate(wallet, "2222222222", "500.01", "")
        assertNotNull(result.errors.amount)
        assertNull(result.amount)
    }

    @Test
    fun `cannot send to the same wallet`() {
        assertNotNull(validate(wallet, "1111111111", "10", "").errors.recipient)
    }

    @Test
    fun `rejects bad account numbers and three-decimal amounts`() {
        val result = validate(wallet, "12345", "1.005", "")
        assertNotNull(result.errors.recipient)
        assertNotNull(result.errors.amount)
    }

    @Test
    fun `below minimum amount`() {
        assertNotNull(validate(wallet, "2222222222", "0.50", "").errors.amount)
    }
}
