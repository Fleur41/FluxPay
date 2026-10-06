package com.fluxpay.feature.business.presentation

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.RequestQuote
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.fluxpay.core.domain.model.BookCategory
import com.fluxpay.core.domain.model.BookEntry
import com.fluxpay.core.domain.model.Invoice
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.feature.business.presentation.components.AmountRow
import com.fluxpay.feature.business.presentation.components.StatCard
import com.fluxpay.feature.business.presentation.components.StatusPill
import com.fluxpay.feature.business.presentation.components.Tone
import com.fluxpay.feature.business.presentation.components.money
import com.fluxpay.feature.business.presentation.viewmodel.Books

private fun invoiceTone(invoice: Invoice) = when {
    invoice.status == "PAID" -> Tone.GOOD
    invoice.status == "CANCELLED" -> Tone.QUIET
    invoice.isOverdue -> Tone.BAD
    else -> Tone.WAIT
}

/**
 * The Bills & invoices tab: what the business owes (bills: payables) and is owed (invoices: receivables).
 * Money still only moves through the cashbook; a bill or invoice is paid by linking the cashbook entry that paid it.
 */
internal fun LazyListScope.billsAndInvoices(
    books: Books,
    canEdit: Boolean,
    onNew: (isBill: Boolean) -> Unit,
    onOpen: (Invoice) -> Unit,
    onOpenOnly: (Boolean) -> Unit,
) {
    val currency = books.invoices.currency
    val totals = books.invoices.totals
    item {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("We owe (bills)", money(totals.payable, currency), Modifier.weight(1f),
                footer = totals.payableOverdue.takeIf { it.signum() > 0 }?.let { "${money(it, currency)} overdue" })
            StatCard("Owed to us (invoices)", money(totals.receivable, currency), Modifier.weight(1f),
                footer = totals.receivableOverdue.takeIf { it.signum() > 0 }?.let { "${money(it, currency)} overdue" })
        }
    }
    if (canEdit) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { onNew(true) }, Modifier.weight(1f)) { Text("+ Bill to pay") }
                OutlinedButton(onClick = { onNew(false) }, Modifier.weight(1f)) { Text("+ Invoice to collect") }
            }
        }
    }
    item {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = books.openOnly, onClick = { onOpenOnly(true) }, label = { Text("Not paid") })
            FilterChip(selected = !books.openOnly, onClick = { onOpenOnly(false) }, label = { Text("All") })
        }
    }
    if (books.invoices.items.isEmpty()) {
        item {
            EmptyState(Icons.Outlined.RequestQuote, if (books.openOnly) "Nothing owed" else "No bills or invoices yet",
                "Record a supplier's bill you haven't paid yet, or an invoice a customer hasn't paid you, to see " +
                    "what's owed each way.")
        }
    }
    items(books.invoices.items, key = { it.id }) { invoice ->
        Row(
            Modifier.fillMaxWidth().clickable { onOpen(invoice) }.padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(invoice.party, maxLines = 1)
                Text(
                    listOfNotNull(
                        invoice.number,
                        if (invoice.isBill) "we owe" else "owed to us",
                        invoice.dueDate?.let { "due $it" },
                    ).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(money(if (invoice.isOpen) invoice.outstanding else invoice.amount, currency), fontWeight = FontWeight.SemiBold)
                StatusPill(if (invoice.isOverdue) "Overdue" else invoice.statusLabel, invoiceTone(invoice))
            }
        }
        HorizontalDivider()
    }
}

/** Recording a bill (an expense we owe) or an invoice (income owed to us). */
@Composable
internal fun NewInvoiceDialog(
    isBill: Boolean,
    categories: List<BookCategory>,
    onSave: (party: String, amount: String, category: BookCategory, description: String, dueDate: String?) -> Unit,
    onDismiss: () -> Unit,
) {
    val options = categories.filter { it.type == if (isBill) "EXPENSE" else "INCOME" }
    var party by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var due by remember { mutableStateOf("") }
    var category by remember { mutableStateOf(options.firstOrNull { it.name.startsWith(if (isBill) "Purchases" else "Sales") } ?: options.firstOrNull()) }
    var choosing by remember { mutableStateOf(false) }
    val dueValid = due.isBlank() || Regex("""\d{4}-\d{2}-\d{2}""").matches(due.trim())
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (isBill) "Bill to pay" else "Invoice to collect") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    if (isBill) "Money the business owes a supplier. It's counted as an expense now and shows as owed " +
                        "until you link the payment from the cashbook."
                    else "Money a customer owes the business. It's counted as income now and shows as owed to you " +
                        "until you link the money they pay in.",
                    style = MaterialTheme.typography.bodySmall,
                )
                FluxTextField(value = party, onValueChange = { party = it }, label = if (isBill) "Supplier" else "Customer")
                FluxTextField(value = amount, onValueChange = { amount = it }, label = "Amount", keyboardType = KeyboardType.Decimal)
                Box {
                    OutlinedButton(onClick = { choosing = true }, Modifier.fillMaxWidth()) {
                        Text("Category: ${category?.name ?: "choose"}")
                    }
                    DropdownMenu(expanded = choosing, onDismissRequest = { choosing = false }) {
                        options.forEach { option ->
                            DropdownMenuItem(text = { Text(option.name) }, onClick = { category = option; choosing = false })
                        }
                    }
                }
                FluxTextField(value = description, onValueChange = { description = it }, label = "What for (optional)")
                FluxTextField(value = due, onValueChange = { due = it }, label = "Due date (optional)",
                    supportingText = "Like 2026-10-31", error = if (dueValid) null else "Use year-month-day, e.g. 2026-10-31")
            }
        },
        confirmButton = {
            val selected = category
            TextButton(
                onClick = { if (selected != null) onSave(party, amount, selected, description, due.trim().ifBlank { null }) },
                enabled = party.isNotBlank() && amount.isNotBlank() && selected != null && dueValid,
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** One bill or invoice: what's owed, what paid it, and linking a payment or cancelling it. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun InvoiceSheet(
    invoice: Invoice,
    currency: String,
    canEdit: Boolean,
    onLinkPayment: () -> Unit,
    onCancel: () -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${invoice.number} · ${invoice.party}", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                StatusPill(if (invoice.isOverdue) "Overdue" else invoice.statusLabel, invoiceTone(invoice))
            }
            Text(
                listOfNotNull(invoice.category.name, invoice.description.ifBlank { null }).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            AmountRow(if (invoice.isBill) "Bill" else "Invoice", money(invoice.amount, currency))
            AmountRow(if (invoice.isBill) "Paid" else "Received", money(invoice.paid, currency))
            AmountRow("Still owed", money(invoice.outstanding, currency), bold = true)
            Text("Issued ${invoice.issueDate}" + (invoice.dueDate?.let { " · due $it" } ?: ""), style = MaterialTheme.typography.bodySmall)
            if (invoice.payments.isNotEmpty()) {
                Text(if (invoice.isBill) "Paid by" else "Received", Modifier.padding(top = 8.dp), style = MaterialTheme.typography.titleSmall)
                invoice.payments.forEach { (date, amount, who) -> AmountRow("$date · $who", money(amount, currency)) }
            }
            if (canEdit && invoice.isOpen) {
                FluxPrimaryButton(if (invoice.isBill) "Link the payment from the cashbook" else "Link the money received",
                    onLinkPayment, Modifier.padding(top = 8.dp))
                if (invoice.paid.signum() == 0) {
                    TextButton(onClick = onCancel, Modifier.fillMaxWidth()) {
                        Text("Cancel ${if (invoice.isBill) "bill" else "invoice"}", color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
    }
}

/** Picking the cashbook entry that paid the bill (or the money that came in for the invoice). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun LinkPaymentSheet(
    invoice: Invoice,
    entries: List<BookEntry>?,
    currency: String,
    onPick: (BookEntry) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 32.dp)) {
            Text(if (invoice.isBill) "Which payment paid ${invoice.number}?" else "Which money in paid ${invoice.number}?",
                style = MaterialTheme.typography.titleMedium)
            Text("Up to ${money(invoice.outstanding, currency)}, not already linked to another bill or invoice.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            when {
                entries == null -> Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                entries.isEmpty() -> Text(
                    if (invoice.isBill) "No matching payment yet. Pay ${invoice.party} from the business first, then link it here."
                    else "No matching money in yet. Once ${invoice.party} pays, link it here.",
                    Modifier.padding(vertical = 16.dp),
                )
                else -> Card(Modifier.fillMaxWidth().padding(top = 8.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
                    entries.forEach { entry ->
                        Row(
                            Modifier.fillMaxWidth().clickable { onPick(entry) }.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(entry.counterparty.ifBlank { entry.sourceLabel }, maxLines = 1)
                                Text("${entry.date} · ${entry.category.name}", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Text(money(entry.amount, currency), fontWeight = FontWeight.SemiBold)
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}
