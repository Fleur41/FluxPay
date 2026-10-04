package com.fluxpay.core.data.repository

import org.junit.Assert.assertEquals
import org.junit.Test

class WorkerCsvTest {
    @Test
    fun `reads a spreadsheet export with friendly headers and quoted cells`() {
        val csv = """
            Account Number,Salary,Job Title
            7744963855,"25,000",Cashier

            5770432927,18000,"Driver, night shift"
        """.trimIndent()
        val rows = BusinessRepositoryImpl.parseCsv(csv)
        assertEquals(2, rows.size)
        assertEquals(mapOf("account_number" to "7744963855", "salary" to "25,000", "job_title" to "Cashier"), rows[0])
        assertEquals("Driver, night shift", rows[1]["job_title"])
    }

    @Test
    fun `missing cells become empty`() {
        val rows = BusinessRepositoryImpl.parseCsv("phone_number,salary,job_title\n0711000000,9000")
        assertEquals("", rows.single()["job_title"])
    }
}
