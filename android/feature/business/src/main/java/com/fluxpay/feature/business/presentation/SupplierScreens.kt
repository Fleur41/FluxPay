package com.fluxpay.feature.business.presentation

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.LocalShipping
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.BusinessPayment
import com.fluxpay.core.domain.model.PayoutMethod
import com.fluxpay.core.domain.model.Supplier
import com.fluxpay.core.ui.components.Avatar
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.feature.business.presentation.components.BackTopBar
import com.fluxpay.feature.business.presentation.components.InputDialog
import com.fluxpay.feature.business.presentation.components.StatusPill
import com.fluxpay.feature.business.presentation.components.Tone
import com.fluxpay.feature.business.presentation.components.money
import com.fluxpay.feature.business.presentation.viewmodel.SuppliersViewModel

private val supplierKinds = listOf(
    "SUPPLIER" to "Supplier", "CONTRACTOR" to "Contractor", "LANDLORD" to "Landlord", "UTILITY" to "Utility",
    "SERVICE_PROVIDER" to "Service provider", "OTHER" to "Other",
)

private fun paymentTone(payment: BusinessPayment) = when (payment.status) {
    "COMPLETED" -> Tone.GOOD
    "PENDING_APPROVAL", "PENDING", "PROCESSING" -> Tone.WAIT
    "FAILED", "REJECTED", "REVERSED" -> Tone.BAD
    else -> Tone.QUIET
}

/**
 * Paying suppliers, contractors, the landlord... from the business cashbook. A supplier is saved once with how to
 * pay them; an owner or admin checks those details before the first payment. Payments above the approval limit wait
 * for an owner or admin. Each payment lands in the cashbook, where it can be linked to the supplier's bill.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SuppliersScreen(onBack: () -> Unit, viewModel: SuppliersViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var tab by remember { mutableIntStateOf(0) }
    var adding by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Supplier?>(null) }
    var paying by remember { mutableStateOf<Supplier?>(null) }
    var deciding by remember { mutableStateOf<Pair<BusinessPayment, String>?>(null) }
    val data = state.data
    val canPay = data?.business?.canPrepare == true
    val canApprove = data?.business?.canApprove == true
    Scaffold(
        topBar = { BackTopBar("Pay suppliers", data?.business?.name, onBack) },
        floatingActionButton = {
            if (canPay && tab == 0) {
                ExtendedFloatingActionButton(onClick = { adding = true }, icon = { Icon(Icons.Outlined.LocalShipping, null) },
                    text = { Text("Add supplier") })
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { d ->
            item {
                TabRow(selectedTabIndex = tab) {
                    Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Suppliers (${d.suppliers.size})") })
                    val waiting = d.payments.count { it.waitingForApproval }
                    Tab(selected = tab == 1, onClick = { tab = 1 },
                        text = { Text("Payments" + if (waiting > 0) " ($waiting to approve)" else "") })
                }
            }
            if (tab == 0) {
                if (d.suppliers.isEmpty()) {
                    item {
                        EmptyState(Icons.Outlined.LocalShipping, "No suppliers yet",
                            "Save a supplier once with how to pay them (M-Pesa, paybill, till, bank or FluxPay), then pay them in a few taps.")
                    }
                }
                items(d.suppliers, key = { it.id }) { supplier ->
                    Row(
                        Modifier.fillMaxWidth().clickable { selected = supplier }.padding(vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Avatar(supplier.name, size = 36)
                        Column(Modifier.weight(1f)) {
                            Text(supplier.name)
                            Text("${supplier.kindLabel} · ${supplier.methodLabel} · ${supplier.details}", maxLines = 1,
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        StatusPill(if (supplier.isVerified) "Checked" else "Needs checking", if (supplier.isVerified) Tone.GOOD else Tone.WAIT)
                    }
                    HorizontalDivider()
                }
            } else {
                if (d.payments.isEmpty()) {
                    item { EmptyState(Icons.Outlined.Payments, "No payments yet", "Payments to suppliers show here.") }
                }
                items(d.payments, key = { it.id }) { payment ->
                    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(payment.recipient.ifBlank { payment.typeLabel })
                                Text(listOfNotNull(payment.date, payment.payoutMethod, payment.note.ifBlank { null },
                                    "by ${payment.createdBy}").joinToString(" · "),
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                payment.failureReason?.takeIf { it.isNotBlank() }?.let {
                                    Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                                }
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text(money(payment.amount, payment.currency), fontWeight = FontWeight.SemiBold)
                                StatusPill(payment.statusLabel, paymentTone(payment))
                            }
                        }
                        if (payment.waitingForApproval) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
                                if (canApprove) {
                                    OutlinedButton(onClick = { deciding = payment to "approve" }) { Text("Approve") }
                                    OutlinedButton(onClick = { deciding = payment to "reject" }) { Text("Reject") }
                                }
                                if (canPay) TextButton(onClick = { deciding = payment to "cancel" }) { Text("Cancel") }
                            }
                        }
                    }
                    HorizontalDivider()
                }
            }
        }
    }
    if (adding) {
        AddSupplierDialog(onSave = { name, kind, method, details -> adding = false; viewModel.add(name, kind, method, details) },
            onDismiss = { adding = false })
    }
    selected?.let { supplier ->
        ModalBottomSheet(onDismissRequest = { selected = null }) {
            Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(supplier.name, style = MaterialTheme.typography.titleMedium)
                Text("${supplier.kindLabel} · ${supplier.methodLabel}", style = MaterialTheme.typography.bodySmall)
                Text(supplier.details, style = MaterialTheme.typography.bodyMedium)
                Text(
                    if (supplier.isVerified) "Payout details checked by ${supplier.verifiedBy}."
                    else "Payout details entered by ${supplier.detailsChangedBy}. An owner or admin must check them " +
                        "(e.g. against the supplier's invoice) before anyone can pay this supplier.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (supplier.isVerified && canPay) {
                    FluxPrimaryButton("Pay ${supplier.name}", { selected = null; paying = supplier }, loading = state.busy)
                }
                if (!supplier.isVerified && canApprove) {
                    FluxPrimaryButton("I've checked these details", { selected = null; viewModel.verify(supplier) })
                }
                if (canPay) {
                    TextButton(onClick = { selected = null; viewModel.archive(supplier) }, Modifier.fillMaxWidth()) {
                        Text("Remove supplier", color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
    }
    paying?.let { supplier ->
        InputDialog("Pay ${supplier.name}",
            "From the business wallet to ${supplier.methodLabel} ${supplier.details}. It goes into the cashbook, where you " +
                "can link it to their bill (Books → Bills & invoices).",
            listOf(Triple("Amount (${data?.currency.orEmpty()})", KeyboardType.Decimal, ""), Triple("Note (optional)", KeyboardType.Text, "")),
            "Pay", onConfirm = { (amount, note) -> paying = null; viewModel.pay(supplier, amount, note) },
            onDismiss = { paying = null })
    }
    deciding?.let { (payment, action) ->
        val title = when (action) { "approve" -> "Approve and pay?"; "reject" -> "Reject this payment?"; else -> "Cancel this payment?" }
        InputDialog(title, "${money(payment.amount, payment.currency)} to ${payment.recipient}, prepared by ${payment.createdBy}.",
            if (action == "cancel") emptyList() else listOf(Triple("Note (optional)", KeyboardType.Text, "")),
            when (action) { "approve" -> "Approve"; "reject" -> "Reject"; else -> "Cancel payment" },
            onConfirm = { values -> deciding = null; viewModel.decide(payment, action, values.firstOrNull().orEmpty()) },
            onDismiss = { deciding = null }, destructive = action != "approve", requireFirst = false)
    }
}

@Composable
private fun AddSupplierDialog(
    onSave: (name: String, kind: String, method: PayoutMethod, details: Map<String, String>) -> Unit,
    onDismiss: () -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("SUPPLIER") }
    var method by remember { mutableStateOf(PayoutMethod.MPESA_MOBILE) }
    val details = remember { mutableStateMapOf<String, String>() }
    val complete = name.isNotBlank() && method.fields.all { (key, _) -> !details[key].isNullOrBlank() || key == "bank_branch" }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add supplier") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FluxTextField(value = name, onValueChange = { name = it }, label = "Name")
                Text("What they are", style = MaterialTheme.typography.labelLarge)
                ChipRow(supplierKinds, kind) { kind = it }
                Text("How to pay them", style = MaterialTheme.typography.labelLarge)
                ChipRow(PayoutMethod.entries.map { it.name to it.label }, method.name) { chosen ->
                    method = PayoutMethod.valueOf(chosen)
                    details.clear()
                }
                method.fields.forEach { (key, label) ->
                    val numeric = key in setOf("mpesa_phone", "paybill_number", "till_number", "account_number")
                    FluxTextField(value = details[key].orEmpty(), onValueChange = { details[key] = it }, label = label,
                        keyboardType = if (numeric) KeyboardType.Number else KeyboardType.Text)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(name, kind, method, details.toMap()) }, enabled = complete) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** A wrapping row of single-choice chips. */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun ChipRow(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { (value, label) ->
            FilterChip(selected = value == selected, onClick = { onSelect(value) }, label = { Text(label) })
        }
    }
}
