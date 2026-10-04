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
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.MenuBook
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.PersonAdd
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
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.BookEntry
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
private fun <T> ScreenBody(
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
    Box(Modifier.padding(padding).fillMaxSize()) {
        when {
            data == null && state.error != null -> ErrorBanner(state.error, Modifier.padding(16.dp), onRetry = onRetry)
            data == null -> FullScreenLoading()
            else -> LazyColumn(contentPadding = listPadding, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                content(data)
            }
        }
        if (state.busy) LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
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
fun BusinessHubScreen(onOpenBusiness: (String) -> Unit, viewModel: BusinessHubViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    Scaffold(topBar = { TopAppBar(title = { Text("Business") }) }, snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { hub ->
            item { SectionTitle("My businesses") }
            if (hub.businesses.isEmpty()) {
                item {
                    EmptyState(Icons.Outlined.Storefront, "No businesses yet",
                        "When a business adds you as owner, admin or finance, it appears here to pay workers and keep its books.")
                }
            }
            items(hub.businesses, key = { it.id }) { business ->
                Card(Modifier.fillMaxWidth().clickable { onOpenBusiness(business.id) },
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
    onWorkers: (String) -> Unit,
    onPayRuns: (String) -> Unit,
    onBooks: (String) -> Unit,
    viewModel: BusinessHomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val id = viewModel.businessId
    Scaffold(
        topBar = { BackTopBar(state.data?.business?.name ?: "Business", state.data?.business?.roleLabel, onBack) },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { home ->
            item {
                StatCard("Business wallet", money(home.wallet.balance, home.wallet.currency), Modifier.fillMaxWidth(),
                    footer = "Account ${home.wallet.accountNumber}. Workers are paid from here.")
            }
            item {
                ActionCard(Icons.Outlined.Badge, "Workers", "${home.workers} on the payroll. Add, import or change salaries.",
                    onClick = { onWorkers(id) })
            }
            item {
                val badge = home.waitingForApproval.takeIf { it > 0 }?.let { "$it to approve" }
                ActionCard(Icons.Outlined.Payments, "Pay workers", "Pay everyone in one go, approve pay runs, take back a wrong payment.",
                    onClick = { onPayRuns(id) }, badge = badge)
            }
            item {
                ActionCard(Icons.Outlined.MenuBook, "Books", "Cashbook, money in and out, profit and balance sheet.",
                    onClick = { onBooks(id) })
            }
            home.payRuns.firstOrNull()?.let { latest ->
                item { SectionTitle("Latest pay run", Modifier.padding(top = 8.dp)) }
                item { PayRunCard(latest) { onPayRuns(id) } }
            }
        }
    }
}

@Composable
private fun PayRunCard(run: PayRun, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick),
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

@Composable
fun WorkersScreen(onBack: () -> Unit, viewModel: WorkersViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var adding by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Worker?>(null) }
    var removing by remember { mutableStateOf<Worker?>(null) }
    val pickCsv = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) scope.launch {
            val text = withContext(Dispatchers.IO) {
                context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
            }
            if (text != null) viewModel.import(text)
        }
    }
    val canEdit = state.data?.business?.canPrepare == true
    Scaffold(
        topBar = {
            BackTopBar("Workers", state.data?.let { "${it.workers.size} on payroll · ${money(it.monthlyPayroll, it.workers.firstOrNull()?.currency ?: "")} a month" }, onBack) {
                if (canEdit) IconButton(onClick = { pickCsv.launch("text/*") }) { Icon(Icons.Outlined.UploadFile, "Import workers from a CSV file") }
            }
        },
        floatingActionButton = {
            if (canEdit) ExtendedFloatingActionButton(onClick = { adding = true }, icon = { Icon(Icons.Outlined.PersonAdd, null) },
                text = { Text("Add worker") })
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { data ->
            item {
                FluxTextField(value = data.search, onValueChange = viewModel::search, label = "Search name, job or account number")
            }
            if (data.workers.isEmpty()) {
                item {
                    EmptyState(Icons.Outlined.Badge, "No workers yet",
                        "Add workers by their FluxPay account number or phone number, or import a CSV file with columns account_number, salary, job_title.")
                }
            }
            items(data.shown, key = { it.id }) { worker ->
                var menu by remember { mutableStateOf(false) }
                Row(Modifier.fillMaxWidth().clickable(enabled = canEdit) { menu = true }.padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Avatar(worker.name, size = 40)
                    Column(Modifier.weight(1f)) {
                        Text(worker.name, style = MaterialTheme.typography.bodyLarge)
                        Text(listOf(worker.jobTitle, worker.accountNumber).filter { it.isNotBlank() }.joinToString(" · "),
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Text(money(worker.salary, worker.currency), style = MaterialTheme.typography.bodyMedium)
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(text = { Text("Change salary") }, onClick = { menu = false; editing = worker })
                        DropdownMenuItem(text = { Text("Remove from payroll") }, onClick = { menu = false; removing = worker })
                    }
                }
                HorizontalDivider()
            }
        }
    }
    if (adding) {
        InputDialog(
            title = "Add worker",
            message = "The worker must have a FluxPay account. Their pay lands in their own wallet.",
            fields = listOf(
                Triple("Account number or phone number", KeyboardType.Phone, ""),
                Triple("Monthly salary", KeyboardType.Decimal, ""),
                Triple("Job title (optional)", KeyboardType.Text, ""),
            ),
            confirm = "Add",
            onConfirm = { (who, salary, job) -> adding = false; viewModel.add(who, salary, job) },
            onDismiss = { adding = false },
        )
    }
    editing?.let { worker ->
        InputDialog("Change salary", worker.name, listOf(Triple("Monthly salary", KeyboardType.Decimal, worker.salary.toPlainString())),
            "Save", onConfirm = { (salary) -> editing = null; viewModel.changeSalary(worker, salary) }, onDismiss = { editing = null })
    }
    removing?.let { worker ->
        InputDialog("Remove ${worker.name}?", "They won't be in future pay runs. Past payslips stay on record.", emptyList(),
            "Remove", onConfirm = { removing = null; viewModel.remove(worker) }, onDismiss = { removing = null }, destructive = true)
    }
}

// --- Pay runs ------------------------------------------------------------------------------------

@Composable
fun PayRunsScreen(onBack: () -> Unit, onOpenRun: (String, String) -> Unit, viewModel: PayRunsViewModel = hiltViewModel()) {
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
fun PayRunDetailScreen(onBack: () -> Unit, viewModel: PayRunDetailViewModel = hiltViewModel()) {
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
                            FluxPrimaryButton("Send pay run (${money(run.total, run.currency)})", { dialog = "submit" }, loading = state.busy)
                            OutlinedButton(onClick = { dialog = "cancel" }, Modifier.fillMaxWidth()) { Text("Cancel draft") }
                            Text("Tap a worker to change their pay or leave them out of this run.",
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        PayRunStatus.PENDING_APPROVAL -> {
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
                Row(Modifier.fillMaxWidth().clickable(enabled = tappable) {
                    if (run.status == PayRunStatus.DRAFT) editing = payslip else reversing = payslip
                }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
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
        "submit" -> InputDialog("Send pay run?", data?.let { "${it.run.workerCount} workers will receive ${money(it.run.total, it.run.currency)} in total. Above your approval limit, an owner or admin must approve first." },
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
fun BooksScreen(onBack: () -> Unit, viewModel: BooksViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var tab by remember { mutableIntStateOf(0) }
    var refiling by remember { mutableStateOf<BookEntry?>(null) }
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
                    Tab(selected = tab == 1, onClick = { tab = 1 }, text = { Text("Profit & balance sheet") })
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
                    Row(Modifier.fillMaxWidth().clickable(enabled = books.business.canPrepare) { refiling = entry }.padding(vertical = 6.dp),
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
            } else {
                val s = books.summary
                item { SummaryBlock("Income", s.income, currency) }
                item { SummaryBlock("Expenses", s.expenses, currency) }
                item { AmountRow(if (s.profit.signum() >= 0) "Profit" else "Loss", money(s.profit, currency), bold = true) }
                item { SectionTitle("Balance sheet", Modifier.padding(top = 12.dp)) }
                item { SummaryBlock("What the business has", s.assets, currency) }
                item { SummaryBlock("Owners' equity", s.equity, currency) }
                item {
                    StatusPill(if (s.balanced) "Balances: assets = equity" else "Does not balance", if (s.balanced) Tone.GOOD else Tone.BAD)
                }
            }
        }
    }
    refiling?.let { entry ->
        val categories = state.data?.categories.orEmpty().filter {
            if (entry.isMoneyIn) it.type in setOf("INCOME", "EQUITY", "EXPENSE") else it.type in setOf("EXPENSE", "EQUITY", "INCOME")
        }
        ModalBottomSheet(onDismissRequest = { refiling = null }) {
            Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 32.dp)) {
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
