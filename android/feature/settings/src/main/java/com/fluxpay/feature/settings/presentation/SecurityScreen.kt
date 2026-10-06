package com.fluxpay.feature.settings.presentation

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.MfaSetup
import com.fluxpay.core.domain.model.MfaStatus
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.core.ui.components.FluxPasswordField
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxSecondaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.core.ui.components.FullScreenLoading
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SecurityUiState(
    val status: MfaStatus? = null,
    /** Setting up: the secret to add to the authenticator app. */
    val setup: MfaSetup? = null,
    val code: String = "",
    /** Just turned on (or replaced): shown once. */
    val recoveryCodes: List<String>? = null,
    val busy: Boolean = false,
    val error: String? = null,
    val message: String? = null,
)

@HiltViewModel
class SecurityViewModel @Inject constructor(private val auth: AuthRepository) : ViewModel() {
    private val _state = MutableStateFlow(SecurityUiState())
    val state: StateFlow<SecurityUiState> = _state.asStateFlow()

    init { load() }

    fun load() {
        viewModelScope.launch {
            when (val result = auth.mfaStatus()) {
                is NetworkResult.Success -> _state.update { it.copy(status = result.data, error = null) }
                is NetworkResult.Error -> _state.update { it.copy(error = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun startSetup() = run { auth.startMfaSetup().also { r -> if (r is NetworkResult.Success) _state.update { it.copy(setup = r.data) } } }

    fun onCode(code: String) = _state.update { it.copy(code = code.take(20), error = null) }

    fun enable() = run {
        auth.enableMfa(_state.value.code).also { r ->
            if (r is NetworkResult.Success) _state.update { it.copy(recoveryCodes = r.data, setup = null, code = "") }
        }
    }

    fun newRecoveryCodes(code: String) = run {
        auth.newRecoveryCodes(code).also { r -> if (r is NetworkResult.Success) _state.update { it.copy(recoveryCodes = r.data) } }
    }

    fun disable(password: String, code: String) = run {
        auth.disableMfa(password, code).also { r ->
            if (r is NetworkResult.Success) _state.update { it.copy(message = "Two-step verification is off") }
        }
    }

    fun savedRecoveryCodes() {
        _state.update { it.copy(recoveryCodes = null) }
        load()
    }

    fun messageShown() = _state.update { it.copy(message = null) }

    fun noAuthenticatorApp() = _state.update {
        it.copy(error = "No authenticator app found on this phone. Install one (e.g. Google Authenticator), or type the key into the one you use.")
    }

    private fun run(block: suspend () -> NetworkResult<*>) {
        viewModelScope.launch {
            _state.update { it.copy(busy = true, error = null) }
            val result = block()
            _state.update { it.copy(busy = false, error = (result as? NetworkResult.Error)?.message) }
            if (result is NetworkResult.Success && _state.value.recoveryCodes == null && _state.value.setup == null) load()
        }
    }
}

/**
 * Two-step verification: a code from an authenticator app on top of the password. Needed by business owners
 * and admins to manage a business; anyone can turn it on.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SecurityScreen(onBack: () -> Unit, viewModel: SecurityViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    var turningOff by remember { mutableStateOf(false) }
    var replacingCodes by remember { mutableStateOf(false) }
    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); viewModel.messageShown() }
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Two-step verification") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        val status = state.status
        if (status == null && state.error == null) {
            FullScreenLoading(Modifier.padding(padding))
            return@Scaffold
        }
        Column(
            Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            state.error?.let { ErrorBanner(it) }
            val codes = state.recoveryCodes
            val setup = state.setup
            when {
                codes != null -> {
                    Text("Save your recovery codes", style = MaterialTheme.typography.titleLarge)
                    Text("If you lose your phone, each of these codes signs you in once. Keep them somewhere safe, " +
                        "not on this phone. They won't be shown again.", style = MaterialTheme.typography.bodyMedium)
                    Card(Modifier.fillMaxWidth()) {
                        Text(codes.joinToString("\n"), Modifier.padding(16.dp), fontFamily = FontFamily.Monospace,
                            style = MaterialTheme.typography.bodyLarge)
                    }
                    FluxSecondaryButton("Copy codes", { copy(context, "FluxPay recovery codes", codes.joinToString("\n")) })
                    FluxPrimaryButton("I've saved them", viewModel::savedRecoveryCodes)
                }
                setup != null -> {
                    Text("Add FluxPay to your authenticator app", style = MaterialTheme.typography.titleLarge)
                    Text("1. Open it in your authenticator app (Google Authenticator, Microsoft Authenticator, ...), " +
                        "or add an account there with this key:", style = MaterialTheme.typography.bodyMedium)
                    FluxSecondaryButton("Open in authenticator app", {
                        try {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(setup.otpauthUri)))
                        } catch (_: ActivityNotFoundException) {
                            viewModel.noAuthenticatorApp()
                        }
                    })
                    Card(Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(16.dp)) {
                            Text(setup.secret.chunked(4).joinToString(" "), Modifier.weight(1f), fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.SemiBold)
                            TextButton(onClick = { copy(context, "FluxPay key", setup.secret) }) { Text("Copy") }
                        }
                    }
                    Text("2. Enter the 6-digit code the app shows.", style = MaterialTheme.typography.bodyMedium)
                    FluxTextField(value = state.code, onValueChange = viewModel::onCode, label = "Code",
                        keyboardType = KeyboardType.Number, onImeAction = viewModel::enable)
                    FluxPrimaryButton("Turn on", viewModel::enable, enabled = state.code.length >= 6, loading = state.busy)
                }
                status?.enabled == true -> {
                    Text("Two-step verification is on", style = MaterialTheme.typography.titleLarge)
                    Text("Signing in needs your password and a code from your authenticator app. You have " +
                        "${status.recoveryCodesLeft} recovery code${if (status.recoveryCodesLeft == 1) "" else "s"} left.",
                        style = MaterialTheme.typography.bodyMedium)
                    FluxSecondaryButton("Get new recovery codes", { replacingCodes = true })
                    TextButton(onClick = { turningOff = true }) {
                        Text("Turn off", color = MaterialTheme.colorScheme.error)
                    }
                    if (status.required) {
                        Text("You run a business on FluxPay: without two-step verification you can still see it, " +
                            "but not pay, approve or change anything.", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                else -> {
                    Text("Protect your account with a second step", style = MaterialTheme.typography.titleLarge)
                    Text("Signing in will need your password and a 6-digit code from an authenticator app on your phone, " +
                        "so a stolen password isn't enough.", style = MaterialTheme.typography.bodyMedium)
                    if (status?.required == true) {
                        Text("Needed to manage your business: until it's on you can see the business, but not pay, " +
                            "approve or change anything.", style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.error)
                    }
                    FluxPrimaryButton("Set up", viewModel::startSetup, loading = state.busy)
                }
            }
        }
    }
    if (replacingCodes) {
        CodeDialog("New recovery codes", "Your old recovery codes stop working.", needsPassword = false, confirm = "Get new codes",
            onConfirm = { _, code -> replacingCodes = false; viewModel.newRecoveryCodes(code) }, onDismiss = { replacingCodes = false })
    }
    if (turningOff) {
        CodeDialog("Turn off two-step verification?", "Signing in will need only your password.", needsPassword = true,
            confirm = "Turn off", onConfirm = { password, code -> turningOff = false; viewModel.disable(password, code) },
            onDismiss = { turningOff = false })
    }
}

@Composable
private fun CodeDialog(
    title: String,
    message: String,
    needsPassword: Boolean,
    confirm: String,
    onConfirm: (String, String) -> Unit,
    onDismiss: () -> Unit,
) {
    var password by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(message)
                if (needsPassword) FluxPasswordField(value = password, onValueChange = { password = it }, label = "Password")
                FluxTextField(value = code, onValueChange = { code = it }, label = "Code from your app", keyboardType = KeyboardType.Number)
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(password, code) }, enabled = code.isNotBlank() && (!needsPassword || password.isNotBlank())) {
                Text(confirm)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

private fun copy(context: Context, label: String, text: String) {
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))
}
