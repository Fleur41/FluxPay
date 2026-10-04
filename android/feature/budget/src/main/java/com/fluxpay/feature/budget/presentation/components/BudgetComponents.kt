package com.fluxpay.feature.budget.presentation.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.feature.budget.domain.BudgetSummary
import com.fluxpay.feature.budget.domain.GuidelineCheck
import com.fluxpay.feature.budget.presentation.state.LineEditorState
import java.math.BigDecimal

/** Quick-add names offered per section, in the order a Kenyan household budget usually lists them. */
val SUGGESTIONS = mapOf(
    BudgetKind.INCOME to listOf("Salary", "Business", "Side hustle"),
    BudgetKind.NEEDS to listOf("Rent", "Food", "Transport", "Electricity", "Water", "School fees", "Airtime"),
    BudgetKind.WANTS to listOf("Eating out", "Entertainment", "Shopping", "Subscriptions"),
    BudgetKind.SAVINGS to listOf("Emergency fund", "Chama", "SACCO", "Investments"),
)

private fun money(amount: BigDecimal, currency: String) = MoneyFormatter.format(amount, currency)

@Composable
private fun goodColor() = MaterialTheme.colorScheme.primary

@Composable
private fun warnColor() = MaterialTheme.colorScheme.error

/** Neutral, so an empty bar reads as empty (the default track is a tinted colour that looks filled in dark mode). */
@Composable
private fun trackColor() = MaterialTheme.colorScheme.outlineVariant

@Composable
fun SummaryCard(summary: BudgetSummary, currency: String, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Left over each month", style = MaterialTheme.typography.labelLarge)
            Text(
                money(summary.leftOver, currency),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = if (summary.isOverPlanned) warnColor() else MaterialTheme.colorScheme.onSurface,
            )
            if (summary.isOverPlanned) {
                Text(
                    "Your plan spends more than you earn. Trim some needs or wants.",
                    style = MaterialTheme.typography.bodySmall,
                    color = warnColor(),
                )
            }
            HorizontalDivider()
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Figure("Income", money(summary.income, currency))
                Figure("Planned", money(summary.planned, currency))
                Figure("Saving", summary.savingsRatePercent?.let { "$it%" } ?: "–")
            }
        }
    }
}

@Composable
private fun Figure(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleSmall)
    }
}

@Composable
fun MonthSpendingCard(summary: BudgetSummary, currency: String, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Spent this month", style = MaterialTheme.typography.labelLarge)
            val fraction = summary.spentFraction
            if (fraction == null) {
                Text(
                    "${money(summary.spentThisMonth, currency)} so far. Add needs and wants to compare.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                Text(
                    "${money(summary.spentThisMonth, currency)} of ${money(summary.spendingPlan, currency)}",
                    style = MaterialTheme.typography.titleMedium,
                )
                LinearProgressIndicator(
                    progress = { fraction.coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                    color = if (fraction > 1f) warnColor() else goodColor(),
                    trackColor = trackColor(),
                )
                Text(
                    if (fraction > 1f) {
                        "Over your planned needs and wants by ${money(summary.spentThisMonth - summary.spendingPlan, currency)}"
                    } else {
                        "${money(summary.spendingPlan - summary.spentThisMonth, currency)} left to spend"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = if (fraction > 1f) warnColor() else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                "Based on money sent from your wallet this month, as synced to this phone.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
fun GuidelineCard(summary: BudgetSummary, currency: String, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            val targets = summary.guideline.associate { it.kind to it.targetPercent }
            val needs = targets[BudgetKind.NEEDS]
            val wants = targets[BudgetKind.WANTS]
            val savings = targets[BudgetKind.SAVINGS]
            Text("$needs/$wants/$savings check", style = MaterialTheme.typography.labelLarge)
            Text(
                "A rule of thumb: $needs% of income on needs, $wants% on wants, $savings% saved.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            summary.guideline.forEach { GuidelineRow(it, currency) }
        }
    }
}

@Composable
private fun GuidelineRow(check: GuidelineCheck, currency: String) {
    val color: Color = if (check.isHealthy) goodColor() else warnColor()
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(check.kind.label, style = MaterialTheme.typography.bodyMedium)
            Text(
                "${check.sharePercent?.let { "$it%" } ?: "–"} · target ${check.targetPercent}%",
                style = MaterialTheme.typography.bodyMedium,
                color = color,
            )
        }
        LinearProgressIndicator(
            progress = { ((check.sharePercent ?: 0) / 100f).coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth(),
            color = color,
            trackColor = trackColor(),
        )
        Text(money(check.planned, currency), style = MaterialTheme.typography.bodySmall)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun KindSection(
    kind: BudgetKind,
    lines: List<BudgetLine>,
    currency: String,
    onAdd: (label: String) -> Unit,
    onEdit: (BudgetLine) -> Unit,
    modifier: Modifier = Modifier,
) {
    val total = lines.fold(BigDecimal.ZERO) { sum, line -> sum + line.amount }
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(vertical = 8.dp)) {
            Row(
                Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(kind.label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                Text(money(total, currency), style = MaterialTheme.typography.titleSmall)
                TextButton(onClick = { onAdd("") }) {
                    Icon(Icons.Outlined.Add, contentDescription = null)
                    Text("Add")
                }
            }
            lines.forEach { line ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clickable { onEdit(line) }
                        .padding(horizontal = 20.dp, vertical = 12.dp),
                ) {
                    Text(line.label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                    Text(money(line.amount, currency), style = MaterialTheme.typography.bodyLarge)
                }
            }
            val unused = SUGGESTIONS.getValue(kind).filter { name -> lines.none { it.label.equals(name, ignoreCase = true) } }
            if (unused.isNotEmpty()) {
                FlowRow(
                    Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    unused.forEach { name -> AssistChip(onClick = { onAdd(name) }, label = { Text("+ $name") }) }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LineEditorDialog(
    state: LineEditorState,
    currency: String,
    onLabelChange: (String) -> Unit,
    onAmountChange: (String) -> Unit,
    onKindChange: (BudgetKind) -> Unit,
    onSave: () -> Unit,
    onDelete: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (state.isNew) "Add to budget" else "Edit budget line") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BudgetKind.entries.forEach { kind ->
                        FilterChip(selected = state.kind == kind, onClick = { onKindChange(kind) }, label = { Text(kind.label) })
                    }
                }
                OutlinedTextField(
                    value = state.label,
                    onValueChange = onLabelChange,
                    label = { Text("Name") },
                    isError = state.labelError != null,
                    supportingText = state.labelError?.let { error -> { Text(error) } },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = state.amount,
                    onValueChange = onAmountChange,
                    label = { Text("Amount per month") },
                    prefix = { Text("$currency ") },
                    isError = state.amountError != null,
                    supportingText = state.amountError?.let { error -> { Text(error) } },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = { TextButton(onClick = onSave) { Text("Save") } },
        dismissButton = {
            Row {
                if (!state.isNew) {
                    TextButton(onClick = onDelete) { Text("Delete", color = MaterialTheme.colorScheme.error) }
                }
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        },
    )
}
