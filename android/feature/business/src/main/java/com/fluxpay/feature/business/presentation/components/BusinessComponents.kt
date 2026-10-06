package com.fluxpay.feature.business.presentation.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.fluxpay.core.ui.components.FluxTextField
import java.math.BigDecimal
import java.text.NumberFormat
import java.util.Locale

fun money(amount: BigDecimal, currency: String): String {
    val format = NumberFormat.getNumberInstance(Locale.US).apply {
        minimumFractionDigits = 2
        maximumFractionDigits = 2
    }
    val text = format.format(amount.abs())
    return if (amount.signum() < 0) "-$currency $text" else "$currency $text"
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BackTopBar(title: String, subtitle: String? = null, onBack: () -> Unit, actions: @Composable () -> Unit = {}) {
    TopAppBar(
        title = {
            Column {
                Text(title, maxLines = 1)
                if (subtitle != null) {
                    Text(subtitle, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        },
        navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Back") } },
        actions = { actions() },
    )
}

/** A small coloured label, e.g. "Paid" or "Waiting for approval". */
@Composable
fun StatusPill(text: String, tone: Tone) {
    val (container, content) = when (tone) {
        Tone.GOOD -> MaterialTheme.colorScheme.primaryContainer to MaterialTheme.colorScheme.onPrimaryContainer
        Tone.WAIT -> MaterialTheme.colorScheme.tertiaryContainer to MaterialTheme.colorScheme.onTertiaryContainer
        Tone.BAD -> MaterialTheme.colorScheme.errorContainer to MaterialTheme.colorScheme.onErrorContainer
        Tone.QUIET -> MaterialTheme.colorScheme.surfaceVariant to MaterialTheme.colorScheme.onSurfaceVariant
    }
    Surface(color = container, contentColor = content, shape = MaterialTheme.shapes.small) {
        Text(text, Modifier.padding(horizontal = 8.dp, vertical = 2.dp), style = MaterialTheme.typography.labelSmall)
    }
}

enum class Tone { GOOD, WAIT, BAD, QUIET }

@Composable
fun StatCard(label: String, value: String, modifier: Modifier = Modifier, footer: String? = null) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            if (footer != null) Text(footer, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** A big tappable row on the business home: icon, title, explanation, optional count. */
@Composable
fun ActionCard(icon: ImageVector, title: String, text: String, onClick: () -> Unit, badge: String? = null) {
    Card(
        Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = MaterialTheme.shapes.medium) {
                Icon(icon, null, Modifier.padding(10.dp), tint = MaterialTheme.colorScheme.onPrimaryContainer)
            }
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (badge != null) StatusPill(badge, Tone.WAIT)
        }
    }
}

@Composable
fun AmountRow(label: String, amount: String, bold: Boolean = false, color: Color = Color.Unspecified, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(label, Modifier.weight(1f), fontWeight = if (bold) FontWeight.SemiBold else null)
        Text(amount, fontWeight = if (bold) FontWeight.SemiBold else null, color = color)
    }
}

/** A dialog asking for one or more values. `fields` are (label, keyboard, initial value). */
@Composable
fun InputDialog(
    title: String,
    message: String?,
    fields: List<Triple<String, KeyboardType, String>>,
    confirm: String,
    onConfirm: (List<String>) -> Unit,
    onDismiss: () -> Unit,
    destructive: Boolean = false,
    requireFirst: Boolean = true,
    extra: Pair<String, () -> Unit>? = null,
) {
    val values = remember { fields.map { mutableStateOf(it.third) } }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (message != null) Text(message, style = MaterialTheme.typography.bodyMedium)
                fields.forEachIndexed { i, (label, keyboard, _) ->
                    var value by values[i]
                    FluxTextField(value = value, onValueChange = { value = it }, label = label, keyboardType = keyboard)
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(values.map { it.value.trim() }) },
                enabled = !requireFirst || values.firstOrNull()?.value?.isNotBlank() ?: true,
            ) {
                Text(confirm, color = if (destructive) MaterialTheme.colorScheme.error else Color.Unspecified)
            }
        },
        dismissButton = {
            Row {
                if (extra != null) TextButton(onClick = extra.second) { Text(extra.first, color = MaterialTheme.colorScheme.error) }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        },
    )
}
