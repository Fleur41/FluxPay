package com.fluxpay.feature.transfer

import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.CurrencyRule
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

    /** As staff might configure KES in the backend's admin. */
    private val kes = CurrencyRule("KES", "Kenyan Shilling", minTransfer = BigDecimal("10.00"), maxTransfer = BigDecimal("300.00"))

    @Test
    fun `valid form returns parsed amount`() {
        val result = validate(wallet, kes, "2222222222", "250.5", "Lunch")
        assertTrue(result.errors.isValid)
        assertEquals(BigDecimal("250.50"), result.amount)
    }

    @Test
    fun `insufficient funds is caught before calling the server`() {
        val result = validate(wallet, null, "2222222222", "500.01", "")
        assertNotNull(result.errors.amount)
        assertNull(result.amount)
    }

    @Test
    fun `cannot send to the same wallet`() {
        assertNotNull(validate(wallet, kes, "1111111111", "10", "").errors.recipient)
    }

    @Test
    fun `rejects bad account numbers and three-decimal amounts`() {
        val result = validate(wallet, kes, "12345", "1.005", "")
        assertNotNull(result.errors.recipient)
        assertNotNull(result.errors.amount)
    }

    @Test
    fun `limits come from the currency rule`() {
        assertTrue(validate(wallet, kes, "2222222222", "9.99", "").errors.amount!!.startsWith("The minimum is"))
        assertTrue(validate(wallet, kes, "2222222222", "300.01", "").errors.amount!!.startsWith("The most you can send"))
        assertTrue(validate(wallet, kes, "2222222222", "300.00", "").errors.isValid)
    }

    @Test
    fun `without rules loaded the server decides the limits`() {
        assertTrue(validate(wallet, null, "2222222222", "0.50", "").errors.isValid)
        assertNotNull(validate(wallet, null, "2222222222", "0", "").errors.amount)
    }
}
