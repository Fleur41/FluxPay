package com.fluxpay.feature.business.presentation

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.AddBusiness
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.LocalShipping
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.RequestQuote
import androidx.compose.material.icons.outlined.Storefront
import androidx.compose.material.icons.outlined.UploadFile
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.BookEntry
import com.fluxpay.core.domain.model.Invoice
import com.fluxpay.core.domain.model.PayRun
import com.fluxpay.core.domain.model.PayRunStatus
import com.fluxpay.core.domain.model.Payslip
import com.fluxpay.core.domain.model.SummarySection
import com.fluxpay.core.domain.model.Worker
import com.fluxpay.core.ui.components.Avatar
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.core.ui.components.FullScreenLoading
import com.fluxpay.core.ui.components.SectionTitle
import com.fluxpay.feature.business.presentation.components.ActionCard
import com.fluxpay.feature.business.presentation.components.AmountRow
import com.fluxpay.feature.business.presentation.components.BackTopBar
import com.fluxpay.feature.business.presentation.components.InputDialog
import com.fluxpay.feature.business.presentation.components.StatCard
import com.fluxpay.feature.business.presentation.components.StatusPill
import com.fluxpay.feature.business.presentation.components.Tone
import com.fluxpay.feature.business.presentation.components.money
import com.fluxpay.feature.business.presentation.viewmodel.BooksPeriod
import com.fluxpay.feature.business.presentation.viewmodel.BooksViewModel
import com.fluxpay.feature.business.presentation.viewmodel.BusinessHomeViewModel
import com.fluxpay.feature.business.presentation.viewmodel.BusinessHubViewModel
import com.fluxpay.feature.business.presentation.viewmodel.PayRunDetailViewModel
import com.fluxpay.feature.business.presentation.viewmodel.PayRunsViewModel
import com.fluxpay.feature.business.presentation.viewmodel.Screen
import com.fluxpay.feature.business.presentation.viewmodel.WorkersViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private val listPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 96.dp)

/** Shows loading, a load error with retry, one-off messages as a snackbar, and a busy bar while saving. */
@Composable
internal fun <T> ScreenBody(
    state: Screen<T>,
    snackbar: SnackbarHostState,
    padding: PaddingValues,
    onRetry: () -> Unit,
    onMessageShown: () -> Unit,
    content: LazyListScope.(T) -> Unit,
) {
    LaunchedEffect(state.message) {
        state.message?.let {
            snackbar.showSnackbar(it)
            onMessageShown()
        }
    }
    val data = state.data
    Box(Modifier
        .padding(padding)
        .fillMaxSize()) {
        when {
            data == null && state.error != null -> ErrorBanner(state.error, Modifier.padding(16.dp), onRetry = onRetry)
            data == null -> FullScreenLoading()
            else -> LazyColumn(contentPadding = listPadding, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                content(data)
            }
        }
        if (state.busy) LinearProgressIndicator(Modifier
            .fillMaxWidth()
            .align(Alignment.TopCenter))
    }
}

private fun runTone(status: PayRunStatus) = when (status) {
    PayRunStatus.PAID -> Tone.GOOD
    PayRunStatus.PENDING_APPROVAL -> Tone.WAIT
    PayRunStatus.REJECTED -> Tone.BAD
    else -> Tone.QUIET
}

// --- Hub -----------------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BusinessHubScreen(
    onOpenBusiness: (String) -> Unit,
    onNewBusiness: () -> Unit,
    viewModel: BusinessHubViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    Scaffold(
        topBar = { TopAppBar(title = { Text("Business") }) },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = onNewBusiness, icon = { Icon(Icons.Outlined.AddBusiness, null) },
                text = { Text("Start a business") })
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { hub ->
            item { SectionTitle("My businesses") }
            if (hub.businesses.isEmpty()) {
                item {
                    EmptyState(Icons.Outlined.Storefront, "No businesses yet",
                        "Start one, or accept an invitation to help run one, to pay workers and keep its books here.")
                }
            }
            items(hub.businesses, key = { it.id }) { business ->
                Card(Modifier
                    .fillMaxWidth()
                    .clickable { onOpenBusiness(business.id) },
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Avatar(business.name)
                        Column(Modifier.weight(1f)) {
                            Text(business.name, style = MaterialTheme.typography.titleMedium)
                            Text("You are ${business.roleLabel.lowercase()}", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (!business.isActive) StatusPill("Suspended", Tone.BAD)
                    }
                }
            }
            if (hub.payslips.isNotEmpty()) {
                item { SectionTitle("My pay", Modifier.padding(top = 8.dp)) }
                items(hub.payslips, key = { it.id }) { pay ->
                    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
                        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(pay.business, style = MaterialTheme.typography.titleSmall)
                                Text("${pay.title} · ${pay.payDate}", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                                if (pay.isReversed && pay.reversalReason.isNotBlank()) {
                                    Text("Taken back: ${pay.reversalReason}", style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.error)
                                }
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text(money(pay.amount, pay.currency), fontWeight = FontWeight.SemiBold)
                                StatusPill(pay.statusLabel, if (pay.isReversed) Tone.BAD else Tone.GOOD)
                            }
                        }
                    }
                }
            }
        }
    }
}


// --- Business home -------------------------------------------------------------------------------

@Composable
fun BusinessHomeScreen(
    onBack: () -> Unit,
    onWorkers: (String, String?) -> Unit,
    onPayRuns: (String) -> Unit,
    onBooks: (String) -> Unit,
    onTeam: (String) -> Unit,
    onSuppliers: (String) -> Unit,
    onSecurity: () -> Unit,
    viewModel: BusinessHomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val id = viewModel.businessId
    var changingLimit by remember { mutableStateOf(false) }
    if (changingLimit) {
        InputDialog("Approval limit",
            "Pay runs and payments up to this amount go straight out. Above it, a second owner or admin must approve: " +
                "that protects the business if one person makes a mistake or their phone is stolen. Use 0 to approve everything.",
            listOf(Triple("Amount", KeyboardType.Decimal, state.data?.business?.approvalThreshold?.toPlainString() ?: "")),
            "Save", onConfirm = { (amount) -> changingLimit = false; viewModel.setApprovalLimit(amount) },
            onDismiss = { changingLimit = false })
    }
    LaunchedEffect(Unit) { viewModel.load() } // fresh figures after coming back from paying or approving
    Scaffold(
        topBar = { BackTopBar(state.data?.business?.name ?: "Business", state.data?.business?.roleLabel, onBack) },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { home ->
            val currency = home.wallet.currency
            if (home.needsTwoStep) {
                item {
                    ActionCard(Icons.Outlined.Lock, "Turn on two-step verification",
                        "Owners and admins need it to pay, approve or change anything here. You can still look around.",
                        onClick = onSecurity, badge = "Needed")
                }
            }
            item {
                StatCard("Business wallet", money(home.wallet.balance, currency), Modifier.fillMaxWidth(),
                    footer = "Account ${home.wallet.accountNumber}. Customers and owners pay in here; workers and suppliers are paid from it.")
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatCard("In this month", home.monthMoneyIn?.let { money(it, currency) } ?: "…", Modifier.weight(1f))
                    StatCard("Out this month", home.monthMoneyOut?.let { money(it, currency) } ?: "…", Modifier.weight(1f))
                }
            }
            home.month?.let { month ->
                item {
                    StatCard(if (month.profit.signum() >= 0) "Profit this month" else "Loss this month", money(month.profit, currency),
                        Modifier.fillMaxWidth().clickable { onBooks(id) },
                        footer = "Income ${money(month.income.total, currency)} · expenses ${money(month.expenses.total, currency)}. Tap for the books.")
                }
            }

            // Everything waiting on someone, most urgent first.
            val owed = home.owed?.totals
            val attention = buildList {
                if (home.waitingForApproval > 0) add(Triple("${home.waitingForApproval} pay run${if (home.waitingForApproval == 1) "" else "s"} to approve", Icons.Outlined.Payments) { onPayRuns(id) })
                if (home.paymentsToApprove > 0) add(Triple("${home.paymentsToApprove} supplier payment${if (home.paymentsToApprove == 1) "" else "s"} to approve", Icons.Outlined.LocalShipping) { onSuppliers(id) })
                if (home.joinRequests > 0) add(Triple("${home.joinRequests} worker${if (home.joinRequests == 1) "" else "s"} asking to join", Icons.Outlined.Badge) { onWorkers(id, "REQUESTS") })
                if (home.suppliersToCheck > 0) add(Triple("${home.suppliersToCheck} supplier${if (home.suppliersToCheck == 1) "" else "s"} with payout details to check", Icons.Outlined.LocalShipping) { onSuppliers(id) })
                if (owed != null && owed.payableOverdue.signum() > 0) add(Triple("${money(owed.payableOverdue, currency)} of bills overdue", Icons.Outlined.RequestQuote) { onBooks(id) })
                if (owed != null && owed.receivableOverdue.signum() > 0) add(Triple("${money(owed.receivableOverdue, currency)} overdue from customers", Icons.Outlined.RequestQuote) { onBooks(id) })
            }
            if (attention.isNotEmpty()) {
                item { SectionTitle("Needs your attention", Modifier.padding(top = 8.dp)) }
                items(attention) { (text, icon, open) -> ActionCard(icon, text, "Tap to open", onClick = open, badge = "To do") }
            }

            item { SectionTitle("At a glance", Modifier.padding(top = 8.dp)) }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatCard("Workers", "${home.workers}", Modifier.weight(1f).clickable { onWorkers(id, null) },
                        footer = "${money(home.monthlyPayroll, currency)} a month")
                    StatCard("Latest pay run", home.payRuns.firstOrNull()?.statusLabel ?: "None yet",
                        Modifier.weight(1f).clickable { onPayRuns(id) },
                        footer = home.payRuns.firstOrNull()?.let { "${it.title}: ${money(it.total, currency)}" } ?: "Pay everyone in one go")
                }
            }
            if (owed != null) {
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        StatCard("We owe", money(owed.payable, currency), Modifier.weight(1f).clickable { onBooks(id) }, footer = "Unpaid bills")
                        StatCard("Owed to us", money(owed.receivable, currency), Modifier.weight(1f).clickable { onBooks(id) }, footer = "Unpaid invoices")
                    }
                }
            }
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Approval limit: ${money(home.business.approvalThreshold, currency)}", style = MaterialTheme.typography.bodyMedium)
                        Text("Pay runs and payments above this need a second owner or admin to approve.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (home.business.isOwner) TextButton(onClick = { changingLimit = true }) { Text("Change") }
                }
            }

            item { SectionTitle("Manage", Modifier.padding(top = 8.dp)) }
            item { ActionCard(Icons.Outlined.Payments, "Pay workers", "Pay everyone in one go, approve pay runs, take back a wrong payment.", onClick = { onPayRuns(id) }) }
            item { ActionCard(Icons.Outlined.LocalShipping, "Pay suppliers", "Suppliers, contractors and the landlord: by M-Pesa, paybill, till, bank or FluxPay.", onClick = { onSuppliers(id) }) }
            item { ActionCard(Icons.Outlined.Badge, "Workers", "Invite workers, approve requests, change salaries.", onClick = { onWorkers(id, null) }) }
            item { ActionCard(Icons.Outlined.MenuBook, "Books", "Cashbook, bills and invoices, profit and balance sheet.", onClick = { onBooks(id) }) }
            item {
                ActionCard(Icons.Outlined.Groups, "Team",
                    if (home.business.manageableRoles.isEmpty()) "Who helps run the business, and their roles."
                    else "Invite an admin, finance or viewer to help run the business, and change roles.",
                    onClick = { onTeam(id) })
            }

            if (home.recent.isNotEmpty()) {
                item { SectionTitle("Latest in the cashbook", Modifier.padding(top = 8.dp), action = { TextButton(onClick = { onBooks(id) }) { Text("All") } }) }
                items(home.recent, key = { "recent-${it.id}" }) { entry ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(entry.counterparty.ifBlank { entry.sourceLabel }, maxLines = 1)
                            Text("${entry.date} · ${entry.category.name}", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text((if (entry.isMoneyIn) "+" else "−") + money(entry.amount, currency),
                            color = if (entry.isMoneyIn) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                            fontWeight = FontWeight.SemiBold)
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}

/**
 * What happens when this draft is sent, in plain words, and whether sending is blocked: not enough money,
 * or above the approval limit with nobody else allowed to approve (nobody approves their own pay run).
 */
internal fun sendingNote(run: PayRun, businessName: String): Pair<String, Boolean> {
    val limit = money(run.approvalThreshold, run.currency)
    return when {
        run.shortfall.signum() > 0 -> "The business wallet holds ${money(run.walletBalance, run.currency)}; this pay run needs " +
            "${money(run.total, run.currency)}. Add ${money(run.shortfall, run.currency)} to the wallet before sending." to true
        run.needsApproval && run.otherApprovers.isEmpty() -> "This is above the approval limit of $limit, so another owner or " +
            "admin must approve it, and nobody can approve a pay run they prepared. Nobody else in $businessName can approve. " +
            "To pay: have a finance member prepare it so an owner can approve it, add an admin, or raise the approval limit " +
            "on the business page (owners)." to true
        run.needsApproval -> "Above the approval limit of $limit: after you send it, it waits for " +
            "${run.otherApprovers.joinToString(" or ")} to approve. Nobody is paid until then." to false
        else -> "Within the approval limit of $limit: everyone is paid as soon as you send it." to false
    }
}

@Composable
private fun NoteCard(text: String, warning: Boolean) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(
        containerColor = if (warning) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer,
    )) {
        Text(text, Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall,
            color = if (warning) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onSecondaryContainer)
    }
}

@Composable
private fun PayRunCard(run: PayRun, onClick: () -> Unit) {
    Card(Modifier
        .fillMaxWidth()
        .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(run.title, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                StatusPill(run.statusLabel, runTone(run.status))
            }
            Text("${run.workerCount} workers · ${money(run.total, run.currency)} · pay date ${run.payDate}",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (run.reversedCount > 0) {
                Text("${run.reversedCount} taken back (${money(run.reversedTotal, run.currency)})",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
        }
    }
}

// --- Workers -------------------------------------------------------------------------------------

// --- Pay runs ------------------------------------------------------------------------------------

@Composable
fun PayRunsScreen(
    onBack: () -> Unit, onOpenRun: (String, String) -> Unit,
    viewModel: PayRunsViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var creating by remember { mutableStateOf(false) }
    LaunchedEffect(state.data?.createdRunId) {
        state.data?.createdRunId?.let { onOpenRun(viewModel.businessId, it); viewModel.opened() }
    }
    LaunchedEffect(Unit) { viewModel.load() } // fresh after returning from a run
    Scaffold(
        topBar = { BackTopBar("Pay workers", state.data?.business?.name, onBack) },
        floatingActionButton = {
            if (state.data?.business?.canPrepare == true) {
                ExtendedFloatingActionButton(onClick = { creating = true }, icon = { Icon(Icons.Outlined.Payments, null) },
                    text = { Text("New pay run") })
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { data ->
            if (data.runs.isEmpty()) {
                item {
                    EmptyState(Icons.Outlined.Payments, "No pay runs yet",
                        "A pay run pays all your workers at once. Start one, check the amounts, then send it.")
                }
            }
            items(data.runs, key = { it.id }) { run -> PayRunCard(run) { onOpenRun(viewModel.businessId, run.id) } }
        }
    }
    if (creating) {
        InputDialog("New pay run", "Every worker is added at their usual salary. You can change amounts before sending.",
            listOf(Triple("Title", KeyboardType.Text, viewModel.suggestedTitle())), "Create",
            onConfirm = { (title) -> creating = false; viewModel.create(title) }, onDismiss = { creating = false })
    }
}

@Composable
fun PayRunDetailScreen(
    onBack: () -> Unit,
    viewModel: PayRunDetailViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var dialog by remember { mutableStateOf<String?>(null) } // approve / reject / cancel / submit
    var editing by remember { mutableStateOf<Payslip?>(null) }
    var reversing by remember { mutableStateOf<Payslip?>(null) }
    val data = state.data
    Scaffold(
        topBar = { BackTopBar(data?.run?.title ?: "Pay run", data?.run?.statusLabel, onBack) },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { detail ->
            val run = detail.run
            val business = detail.business
            item {
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
                    Column(Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(money(run.total, run.currency), Modifier.weight(1f), style = MaterialTheme.typography.headlineSmall,
                                fontWeight = FontWeight.SemiBold)
                            StatusPill(run.statusLabel, runTone(run.status))
                        }
                        Text("${run.workerCount} workers · pay date ${run.payDate}", style = MaterialTheme.typography.bodySmall)
                        Text("Prepared by ${run.createdByName}" + (run.decidedByName?.let { " · decided by $it" } ?: ""),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (run.reversedCount > 0) {
                            Text("${run.reversedCount} payment${if (run.reversedCount == 1) "" else "s"} taken back: ${money(run.reversedTotal, run.currency)}",
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                        }
                    }
                }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    when (run.status) {
                        PayRunStatus.DRAFT -> if (business.canPrepare) {
                            val (note, blocked) = sendingNote(run, business.name)
                            NoteCard(note, warning = blocked)
                            FluxPrimaryButton("Send pay run (${money(run.total, run.currency)})", { dialog = "submit" },
                                loading = state.busy, enabled = !blocked)
                            OutlinedButton(onClick = { dialog = "cancel" }, Modifier.fillMaxWidth()) { Text("Cancel draft") }
                            Text("Tap a worker to change their pay or leave them out of this run.",
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        PayRunStatus.PENDING_APPROVAL -> {
                            if (run.otherApprovers.isEmpty()) {
                                NoteCard("Nobody else in ${business.name} can approve this: approval needs an owner or admin " +
                                    "other than ${run.createdByName}, who prepared it. Cancel it and have a finance member prepare it " +
                                    "instead, add an admin, or raise the approval limit.", warning = true)
                            }
                            if (business.canApprove) {
                                FluxPrimaryButton("Approve and pay everyone", { dialog = "approve" }, loading = state.busy)
                                OutlinedButton(onClick = { dialog = "reject" }, Modifier.fillMaxWidth()) { Text("Reject") }
                            } else {
                                Text("Waiting for an owner or admin to approve.", style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                        PayRunStatus.PAID -> if (business.canApprove) {
                            Text("Paid in error? Tap a worker to take their pay back while they still have it.",
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        else -> Unit
                    }
                }
            }
            item { FluxTextField(value = detail.search, onValueChange = viewModel::search, label = "Find a worker") }
            items(detail.shown, key = { it.id }) { payslip ->
                val tappable = (run.status == PayRunStatus.DRAFT && business.canPrepare) ||
                    (run.status == PayRunStatus.PAID && payslip.isPaid && business.canApprove)
                Row(Modifier
                    .fillMaxWidth()
                    .clickable(enabled = tappable) {
                        if (run.status == PayRunStatus.DRAFT) editing = payslip else reversing =
                            payslip
                    }
                    .padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Avatar(payslip.workerName, size = 36)
                    Column(Modifier.weight(1f)) {
                        Text(payslip.workerName)
                        val sub = if (payslip.isReversed) "Taken back: ${payslip.reversalReason}" else
                            listOf(payslip.jobTitle, payslip.accountNumber).filter { it.isNotBlank() }.joinToString(" · ")
                        Text(sub, style = MaterialTheme.typography.bodySmall,
                            color = if (payslip.isReversed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(money(payslip.amount, run.currency))
                        if (run.status == PayRunStatus.PAID) StatusPill(payslip.statusLabel, if (payslip.isReversed) Tone.BAD else Tone.GOOD)
                    }
                }
                HorizontalDivider()
            }
        }
    }
    when (dialog) {
        "submit" -> InputDialog("Send pay run?", data?.let { "${it.run.workerCount} workers will receive ${money(it.run.total, it.run.currency)} in total. ${sendingNote(it.run, it.business.name).first}" },
            emptyList(), "Send", onConfirm = { dialog = null; viewModel.submit() }, onDismiss = { dialog = null })
        "approve" -> InputDialog("Approve and pay?", "Money leaves the business wallet now and lands in every worker's wallet.",
            listOf(Triple("Note (optional)", KeyboardType.Text, "")), "Approve",
            onConfirm = { (note) -> dialog = null; viewModel.approve(note) }, onDismiss = { dialog = null }, requireFirst = false)
        "reject" -> InputDialog("Reject pay run?", "Nobody is paid. Tell the preparer why.",
            listOf(Triple("Reason", KeyboardType.Text, "")), "Reject",
            onConfirm = { (note) -> dialog = null; viewModel.reject(note) }, onDismiss = { dialog = null }, destructive = true)
        "cancel" -> InputDialog("Cancel this draft?", "Nobody is paid. You can start a new pay run any time.", emptyList(), "Cancel draft",
            onConfirm = { dialog = null; viewModel.cancel() }, onDismiss = { dialog = null }, destructive = true)
    }
    editing?.let { payslip ->
        InputDialog("Pay for ${payslip.workerName}", "Change this month's amount (e.g. overtime or a deduction).",
            listOf(Triple("Amount", KeyboardType.Decimal, payslip.amount.toPlainString())), "Save",
            onConfirm = { (amount) -> editing = null; viewModel.editAmount(payslip, amount) }, onDismiss = { editing = null },
            extra = "Leave out" to { editing = null; viewModel.leaveOut(payslip) })
    }
    reversing?.let { payslip ->
        InputDialog("Take back ${payslip.workerName}'s pay?",
            "${money(payslip.amount, data?.run?.currency ?: "")} returns to the business wallet if they still have it. They are told by SMS and email.",
            listOf(Triple("Why? (required)", KeyboardType.Text, "")), "Take back",
            onConfirm = { (reason) -> reversing = null; viewModel.reverse(payslip, reason) }, onDismiss = { reversing = null }, destructive = true)
    }
}

// --- Books ---------------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BooksScreen(
    onBack: () -> Unit,
    viewModel: BooksViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var tab by remember { mutableIntStateOf(0) }
    var refiling by remember { mutableStateOf<BookEntry?>(null) }
    var newInvoice by remember { mutableStateOf<Boolean?>(null) } // true: a bill, false: an invoice
    var opened by remember { mutableStateOf<Invoice?>(null) }
    var linking by remember { mutableStateOf<Invoice?>(null) }
    var cancelling by remember { mutableStateOf<Invoice?>(null) }
    Scaffold(
        topBar = { BackTopBar("Books", state.data?.business?.name, onBack) },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { books ->
            val currency = books.cashbook.currency
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BooksPeriod.entries.forEach { period ->
                        FilterChip(selected = books.period == period, onClick = { viewModel.choose(period) }, label = { Text(period.label) })
                    }
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatCard("Money in", money(books.cashbook.moneyIn, currency), Modifier.weight(1f))
                    StatCard("Money out", money(books.cashbook.moneyOut, currency), Modifier.weight(1f))
                }
            }
            item {
                StatCard(if (books.summary.profit.signum() >= 0) "Profit" else "Loss", money(books.summary.profit, currency),
                    Modifier.fillMaxWidth(), footer = "Income less expenses for ${books.period.label.lowercase()}")
            }
            item {
                TabRow(selectedTabIndex = tab) {
                    Tab(selected = tab == 0, onClick = { tab = 0 }, text = { Text("Cashbook") })
                    Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Bills & invoices") })
                    Tab(selected = tab == 2, onClick = { tab = 2 }, text = { Text("Reports") })
                }
            }
            if (tab == 0) {
                item {
                    AmountRow("Opening balance", money(books.cashbook.opening, currency))
                    AmountRow("Closing balance (= wallet)", money(books.cashbook.closing, currency), bold = true)
                    Text("Tap an entry to file it under a different category.", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (books.cashbook.entries.isEmpty()) {
                    item { EmptyState(Icons.Outlined.AccountBalanceWallet, "No money moved", "Nothing in or out in this period.") }
                }
                items(books.cashbook.entries, key = { it.id }) { entry ->
                    Row(Modifier
                        .fillMaxWidth()
                        .clickable(enabled = books.business.canPrepare) { refiling = entry }
                        .padding(vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(entry.counterparty.ifBlank { entry.sourceLabel }, maxLines = 1)
                            Text("${entry.date} · ${entry.category.name}", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (entry.description.isNotBlank()) {
                                Text(entry.description, style = MaterialTheme.typography.bodySmall, maxLines = 1,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text((if (entry.isMoneyIn) "+" else "−") + money(entry.amount, currency),
                                color = if (entry.isMoneyIn) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                                fontWeight = FontWeight.SemiBold)
                            Text("Bal ${money(entry.balance, currency)}", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    HorizontalDivider()
                }
            } else if (tab == 1) {
                billsAndInvoices(books, books.business.canPrepare, onNew = { newInvoice = it }, onOpen = { opened = it },
                    onOpenOnly = viewModel::showOpenOnly)
            } else {
                val s = books.summary
                item { SummaryBlock("Income", s.income, currency) }
                item { SummaryBlock("Expenses", s.expenses, currency) }
                item { AmountRow(if (s.profit.signum() >= 0) "Profit" else "Loss", money(s.profit, currency), bold = true) }
                item { SectionTitle("Balance sheet", Modifier.padding(top = 12.dp)) }
                item { SummaryBlock("What the business has", s.assets, currency) }
                if (s.liabilities.lines.isNotEmpty()) item { SummaryBlock("What the business owes", s.liabilities, currency) }
                item { SummaryBlock("Owners' equity", s.equity, currency) }
                item {
                    StatusPill(if (s.balanced) "Balances: assets = liabilities + equity" else "Does not balance",
                        if (s.balanced) Tone.GOOD else Tone.BAD)
                }
            }
        }
    }
    val currency = state.data?.invoices?.currency.orEmpty()
    newInvoice?.let { isBill ->
        NewInvoiceDialog(isBill, state.data?.categories.orEmpty(),
            onSave = { party, amount, category, description, due ->
                newInvoice = null
                viewModel.record(isBill, party, amount, category, description, due)
            },
            onDismiss = { newInvoice = null })
    }
    opened?.let { invoice ->
        InvoiceSheet(invoice, currency, state.data?.business?.canPrepare == true,
            onLinkPayment = { opened = null; linking = invoice; viewModel.findPayments(invoice) },
            onCancel = { opened = null; cancelling = invoice },
            onDismiss = { opened = null })
    }
    linking?.let { invoice ->
        LinkPaymentSheet(invoice, state.data?.payable, currency,
            onPick = { entry -> linking = null; viewModel.pay(invoice, entry) },
            onDismiss = { linking = null })
    }
    cancelling?.let { invoice ->
        InputDialog("Cancel ${invoice.number}?", "Use this when it was recorded by mistake. It comes out of the books.",
            listOf(Triple("Why? (required)", KeyboardType.Text, "")), "Cancel ${if (invoice.isBill) "bill" else "invoice"}",
            onConfirm = { (reason) -> cancelling = null; viewModel.cancel(invoice, reason) },
            onDismiss = { cancelling = null }, destructive = true)
    }
    refiling?.let { entry ->
        val categories = state.data?.categories.orEmpty().filter {
            if (entry.isMoneyIn) it.type in setOf("INCOME", "EQUITY", "EXPENSE") else it.type in setOf("EXPENSE", "EQUITY", "INCOME")
        }
        ModalBottomSheet(onDismissRequest = { refiling = null }) {
            Column(Modifier
                .padding(horizontal = 16.dp)
                .padding(bottom = 32.dp)) {
                Text("File ${money(entry.amount, state.data?.cashbook?.currency ?: "")} under", style = MaterialTheme.typography.titleMedium)
                Text(entry.counterparty, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                categories.forEach { category ->
                    TextButton(onClick = { refiling = null; viewModel.refile(entry, category) }, Modifier.fillMaxWidth()) {
                        Text("${category.name}" + if (category.id == entry.category.id) "  ✓" else "", Modifier.fillMaxWidth())
                    }
                }
            }
        }
    }
}

@Composable
private fun SummaryBlock(title: String, section: SummarySection, currency: String) {
    Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            if (section.lines.isEmpty()) Text("None", style = MaterialTheme.typography.bodySmall)
            section.lines.forEach { AmountRow(it.name, money(it.amount, currency)) }
            HorizontalDivider(Modifier.padding(vertical = 4.dp))
            AmountRow("Total", money(section.total, currency), bold = true)
        }
    }
}
