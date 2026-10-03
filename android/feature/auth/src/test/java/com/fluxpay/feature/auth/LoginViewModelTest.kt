package com.fluxpay.feature.auth

import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.User
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.feature.auth.domain.usecase.LoginUseCase
import com.fluxpay.feature.auth.domain.usecase.ValidateCredentialsUseCase
import com.fluxpay.feature.auth.presentation.viewmodel.LoginViewModel
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class LoginViewModelTest {

    private val dispatcher = StandardTestDispatcher()
    private val repository = mockk<AuthRepository>()
    private lateinit var viewModel: LoginViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
        viewModel = LoginViewModel(ValidateCredentialsUseCase(), LoginUseCase(repository))
    }

    @After
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `invalid email never hits the network`() = runTest(dispatcher) {
        viewModel.onEmailChange("not-an-email")
        viewModel.onPasswordChange("secret123")
        viewModel.submit()
        advanceUntilIdle()
        assertNotNull(viewModel.state.value.errors.email)
        coVerify(exactly = 0) { repository.login(any(), any()) }
    }

    @Test
    fun `server error is surfaced and loading resets`() = runTest(dispatcher) {
        coEvery { repository.login(any(), any()) } returns
            NetworkResult.Error("No active account found with the given credentials", httpStatus = 401)
        viewModel.onEmailChange("amina@fluxpay.dev")
        viewModel.onPasswordChange("wrong-pass")
        viewModel.submit()
        advanceUntilIdle()
        val state = viewModel.state.value
        assertFalse(state.isLoading)
        assertEquals("No active account found with the given credentials", state.errorMessage)
    }

    @Test
    fun `success clears password`() = runTest(dispatcher) {
        coEvery { repository.login(any(), any()) } returns NetworkResult.Success(User("1", "a@b.co", "A B", ""))
        viewModel.onEmailChange("a@b.co")
        viewModel.onPasswordChange("FluxPay#2026")
        viewModel.submit()
        advanceUntilIdle()
        assertEquals("", viewModel.state.value.password)
    }
}
