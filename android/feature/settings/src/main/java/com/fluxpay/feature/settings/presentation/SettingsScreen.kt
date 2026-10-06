package com.fluxpay.feature.settings.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.AddBusiness
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.DarkMode
import androidx.compose.material.icons.outlined.Email
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.Sms
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.ThemeMode
import com.fluxpay.core.ui.components.Avatar
import com.fluxpay.core.ui.components.FluxSecondaryButton
import com.fluxpay.feature.settings.presentation.components.SettingsRow
import com.fluxpay.feature.settings.presentation.components.SettingsSection
import com.fluxpay.feature.settings.presentation.viewmodel.SettingsViewModel

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun SettingsScreen(
    onOpenEmployers: () -> Unit,
    onStartBusiness: () -> Unit,
    onJoinTeam: () -> Unit,
    onOpenSecurity: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var confirmLogout by rememberSaveable { mutableStateOf(false) }
    val scrollState = rememberScrollState()

    Scaffold(topBar = { TopAppBar(title = { Text("Settings") }) }) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            state.user?.let { user ->
                Card(Modifier.fillMaxWidth()) {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Avatar(user.fullName, size = 56)
                        Spacer(Modifier.width(16.dp))
                        Column {
                            Text(user.fullName, style = MaterialTheme.typography.titleMedium)
                            Text(user.email, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (user.phoneNumber.isNotBlank()) {
                                Text(user.phoneNumber, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }

            SettingsSection("Money") {
                SettingsRow(Icons.Outlined.Payments, "Preferred currency", "Used for your dashboard total")
                FlowRow(
                    Modifier.padding(start = 56.dp, end = 16.dp, bottom = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    state.currencies.forEach { code ->
                        FilterChip(
                            selected = state.selectedCurrency == code,
                            onClick = { viewModel.setCurrency(code) },
                            label = { Text(code) },
                        )
                    }
                }
                SettingsRow(
                    icon = Icons.Outlined.VisibilityOff,
                    title = "Hide balances",
                    subtitle = "Mask amounts across the app",
                ) {
                    Switch(checked = state.preferences.hideBalances, onCheckedChange = viewModel::setHideBalances)
                }
            }

            SettingsSection("Security") {
                SettingsRow(
                    icon = Icons.Outlined.Lock,
                    title = "Two-step verification",
                    subtitle = "A code from an authenticator app when you sign in. Needed to manage a business",
                    onClick = onOpenSecurity,
                ) { Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null) }
            }

            SettingsSection("Work") {
                SettingsRow(
                    icon = Icons.Outlined.Badge,
                    title = "My employers",
                    subtitle = "Businesses that pay you. Join one with a code or QR code",
                    onClick = onOpenEmployers,
                ) { Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null) }
                SettingsRow(
                    icon = Icons.Outlined.AddBusiness,
                    title = "Start a business",
                    subtitle = "Its own wallet to pay workers and suppliers, and its own books",
                    onClick = onStartBusiness,
                ) { Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null) }
                SettingsRow(
                    icon = Icons.Outlined.Groups,
                    title = "Join a business team",
                    subtitle = "Invited to help run a business? Accept with the link from the email",
                    onClick = onJoinTeam,
                ) { Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null) }
            }

            SettingsSection("Transaction alerts") {
                SettingsRow(
                    icon = Icons.Outlined.Email,
                    title = "Email alerts",
                    subtitle = state.user?.email ?: "Every payment in or out",
                ) {
                    Switch(
                        checked = state.alerts.emailEnabled == true,
                        onCheckedChange = viewModel::setEmailAlerts,
                        enabled = state.alerts.emailEnabled != null,
                    )
                }
                SettingsRow(
                    icon = Icons.Outlined.Sms,
                    title = "SMS alerts",
                    subtitle = state.user?.phoneNumber?.takeIf { it.isNotBlank() }
                        ?: "Add a phone number to your profile to get SMS alerts",
                ) {
                    Switch(
                        checked = state.alerts.smsEnabled == true,
                        onCheckedChange = viewModel::setSmsAlerts,
                        enabled = state.alerts.smsEnabled != null,
                    )
                }
                state.alerts.error?.let { error ->
                    Row(
                        Modifier.padding(start = 56.dp, end = 16.dp, bottom = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            error,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                            modifier = Modifier.weight(1f),
                        )
                        TextButton(onClick = viewModel::loadAlerts) { Text("Retry") }
                    }
                }
            }

            SettingsSection("Appearance") {
                SettingsRow(Icons.Outlined.DarkMode, "Theme")
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(start = 56.dp, end = 16.dp, bottom = 12.dp)) {
                    val modes = ThemeMode.entries
                    modes.forEachIndexed { index, mode ->
                        SegmentedButton(
                            selected = state.preferences.themeMode == mode,
                            onClick = { viewModel.setTheme(mode) },
                            shape = SegmentedButtonDefaults.itemShape(index, modes.size),
                        ) { Text(mode.name.lowercase().replaceFirstChar(Char::uppercase)) }
                    }
                }
            }

            SettingsSection("About") {
                SettingsRow(
                    Icons.Outlined.Info,
                    "FluxPay ${state.appVersion}",
                    "Environment: ${state.environment}",
                )
            }

            FluxSecondaryButton(
                text = if (state.isLoggingOut) "Signing out…" else "Sign out",
                onClick = { confirmLogout = true },
                enabled = !state.isLoggingOut,
            )
        }
    }

    if (confirmLogout) {
        AlertDialog(
            onDismissRequest = { confirmLogout = false },
            icon = { androidx.compose.material3.Icon(Icons.AutoMirrored.Outlined.Logout, contentDescription = null) },
            title = { Text("Sign out?") },
            text = { Text("Your cached balances and history will be removed from this phone.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmLogout = false
                    viewModel.logout()
                }) { Text("Sign out") }
            },
            dismissButton = { TextButton(onClick = { confirmLogout = false }) { Text("Cancel") } },
        )
    }
}
