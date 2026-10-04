package com.fluxpay.feature.auth.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.Email
import androidx.compose.material.icons.outlined.MarkEmailRead
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.core.ui.components.FluxPasswordField
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.feature.auth.presentation.components.AuthScaffold
import com.fluxpay.feature.auth.presentation.viewmodel.ForgotPasswordViewModel
import com.fluxpay.feature.auth.presentation.viewmodel.LoginViewModel
import com.fluxpay.feature.auth.presentation.viewmodel.RegisterViewModel
import com.fluxpay.feature.auth.presentation.viewmodel.ResetPasswordViewModel

@Composable
fun LoginScreen(
    onRegisterClick: () -> Unit,
    onForgotPasswordClick: () -> Unit,
    viewModel: LoginViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    AuthScaffold(title = "Welcome back", subtitle = "Sign in to move money with FluxPay.") {
        state.errorMessage?.let { ErrorBanner(it) }
        FluxTextField(
            value = state.email,
            onValueChange = viewModel::onEmailChange,
            label = "Email",
            error = state.errors.email,
            keyboardType = KeyboardType.Email,
            leadingIcon = Icons.Outlined.Email,
        )
        FluxPasswordField(
            value = state.password,
            onValueChange = viewModel::onPasswordChange,
            label = "Password",
            error = state.errors.password,
            onImeAction = viewModel::submit,
        )
        TextButton(onClick = onForgotPasswordClick, modifier = Modifier.align(Alignment.End)) {
            Text("Forgot password?")
        }
        FluxPrimaryButton(text = "Sign in", onClick = viewModel::submit, loading = state.isLoading)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("New to FluxPay?", style = MaterialTheme.typography.bodyMedium)
            TextButton(onClick = onRegisterClick) { Text("Create an account") }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun RegisterScreen(
    onBack: () -> Unit,
    viewModel: RegisterViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    AuthScaffold(title = "Create your wallet", subtitle = "It takes less than a minute.", onBack = onBack) {
        state.errorMessage?.let { ErrorBanner(it) }
        FluxTextField(
            value = state.fullName,
            onValueChange = viewModel::onFullNameChange,
            label = "Full name",
            error = state.errors.fullName,
            leadingIcon = Icons.Outlined.Badge,
        )
        FluxTextField(
            value = state.email,
            onValueChange = viewModel::onEmailChange,
            label = "Email",
            error = state.errors.email,
            keyboardType = KeyboardType.Email,
            leadingIcon = Icons.Outlined.Email,
        )
        FluxTextField(
            value = state.phone,
            onValueChange = viewModel::onPhoneChange,
            label = "Phone (optional)",
            error = state.errors.phone,
            keyboardType = KeyboardType.Phone,
            leadingIcon = Icons.Outlined.Phone,
        )
        FluxPasswordField(
            value = state.password,
            onValueChange = viewModel::onPasswordChange,
            label = "Password",
            error = state.errors.password,
            imeAction = ImeAction.Next,
        )
        FluxPasswordField(
            value = state.confirmPassword,
            onValueChange = viewModel::onConfirmChange,
            label = "Confirm password",
            error = state.errors.confirmPassword,
            onImeAction = viewModel::submit,
        )
        Text("Wallet currency", style = MaterialTheme.typography.labelLarge)
        if (state.currenciesUnavailable) {
            ErrorBanner(
                message = "Couldn't load the available currencies.",
                offline = true,
                onRetry = viewModel::loadCurrencies,
            )
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            state.currencies.forEach { currency ->
                FilterChip(
                    selected = state.currency == currency.code,
                    onClick = { viewModel.onCurrencyChange(currency.code) },
                    label = { Text(currency.code) },
                )
            }
        }
        FluxPrimaryButton(text = "Create account", onClick = viewModel::submit, loading = state.isLoading)
    }
}

@Composable
fun ForgotPasswordScreen(
    onBack: () -> Unit,
    viewModel: ForgotPasswordViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    AuthScaffold(
        title = "Reset password",
        subtitle = "We'll email you a link that opens straight in the app.",
        onBack = onBack,
    ) {
        val sent = state.sentMessage
        if (sent != null) {
            EmptyState(icon = Icons.Outlined.MarkEmailRead, title = "Check your inbox", message = sent)
            FluxPrimaryButton(text = "Back to sign in", onClick = onBack)
        } else {
            state.errorMessage?.let { ErrorBanner(it) }
            FluxTextField(
                value = state.email,
                onValueChange = viewModel::onEmailChange,
                label = "Email",
                error = state.emailError,
                keyboardType = KeyboardType.Email,
                imeAction = ImeAction.Done,
                onImeAction = viewModel::submit,
                leadingIcon = Icons.Outlined.Email,
            )
            FluxPrimaryButton(text = "Send reset link", onClick = viewModel::submit, loading = state.isLoading)
        }
    }
}

@Composable
fun ResetPasswordScreen(
    onDone: () -> Unit,
    viewModel: ResetPasswordViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    AuthScaffold(title = "Choose a new password", subtitle = "Make it something you don't use anywhere else.") {
        when {
            !state.linkValid -> {
                ErrorBanner("This reset link is incomplete. Request a new one from the sign-in screen.")
                FluxPrimaryButton(text = "Back to sign in", onClick = onDone)
            }
            state.successMessage != null -> {
                EmptyState(icon = Icons.Outlined.MarkEmailRead, title = "Password updated", message = state.successMessage!!)
                FluxPrimaryButton(text = "Sign in", onClick = onDone)
            }
            else -> {
                state.errorMessage?.let { ErrorBanner(it) }
                FluxPasswordField(
                    value = state.password,
                    onValueChange = viewModel::onPasswordChange,
                    label = "New password",
                    error = state.errors.password,
                    imeAction = ImeAction.Next,
                )
                FluxPasswordField(
                    value = state.confirmPassword,
                    onValueChange = viewModel::onConfirmChange,
                    label = "Confirm new password",
                    error = state.errors.confirmPassword,
                    onImeAction = viewModel::submit,
                )
                FluxPrimaryButton(text = "Update password", onClick = viewModel::submit, loading = state.isLoading)
            }
        }
    }
}
