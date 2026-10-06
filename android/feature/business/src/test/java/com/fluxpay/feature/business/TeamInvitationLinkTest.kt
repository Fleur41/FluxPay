package com.fluxpay.feature.business

import com.fluxpay.feature.business.presentation.viewmodel.JoinTeamViewModel.Companion.tokenFrom
import org.junit.Assert.assertEquals
import org.junit.Test

class TeamInvitationLinkTest {
    @Test
    fun `takes the token from the emailed link`() {
        assertEquals("abc-DEF_123", tokenFrom("fluxpay://join-business?token=abc-DEF_123"))
    }

    @Test
    fun `ignores other parameters and surrounding text`() {
        assertEquals("abc", tokenFrom("  https://fluxpay.app/join-business?ref=email&token=abc&x=1\n"))
    }

    @Test
    fun `a bare token is used as it is`() {
        assertEquals("abc-DEF_123", tokenFrom(" abc-DEF_123 "))
    }
}
