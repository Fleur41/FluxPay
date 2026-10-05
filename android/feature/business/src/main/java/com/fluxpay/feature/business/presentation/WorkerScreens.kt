package com.fluxpay.feature.business.presentation

import android.graphics.Bitmap
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.HourglassTop
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.QrCode2
import androidx.compose.material.icons.outlined.QrCodeScanner
import androidx.compose.material.icons.outlined.Storefront
import androidx.compose.material.icons.outlined.UploadFile
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.Employer
import com.fluxpay.core.domain.model.JoinCode
import com.fluxpay.core.domain.model.Worker
import com.fluxpay.core.domain.model.WorkerStatus
import com.fluxpay.core.ui.components.Avatar
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxSecondaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.feature.business.presentation.components.BackTopBar
import com.fluxpay.feature.business.presentation.components.InputDialog
import com.fluxpay.feature.business.presentation.components.StatusPill
import com.fluxpay.feature.business.presentation.components.Tone
import com.fluxpay.feature.business.presentation.components.money
import com.fluxpay.feature.business.presentation.viewmodel.EmployersViewModel
import com.fluxpay.feature.business.presentation.viewmodel.JoinBusinessViewModel
import com.fluxpay.feature.business.presentation.viewmodel.WorkerTab
import com.fluxpay.feature.business.presentation.viewmodel.WorkersViewModel
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// --- The business's side: the worker register -----------------------------------------------------

private fun workerTone(status: WorkerStatus) = when (status) {
    WorkerStatus.ACTIVE -> Tone.GOOD
    WorkerStatus.INVITED, WorkerStatus.PENDING_ACTIVATION -> Tone.WAIT
    WorkerStatus.SUSPENDED -> Tone.BAD
    else -> Tone.QUIET
}

/**
 * The register, by status: active workers, invitations not yet accepted, requests to join, and suspended workers.
 * Owners, admins and finance invite and manage; owners and admins approve requests and run the join code.
 */
@Composable
fun WorkersScreen(onBack: () -> Unit, viewModel: WorkersViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var inviting by remember { mutableStateOf(false) }
    var showJoinCode by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<Worker?>(null) }
    var removing by remember { mutableStateOf<Worker?>(null) }
    var approving by remember { mutableStateOf<Worker?>(null) }
    var declining by remember { mutableStateOf<Worker?>(null) }
    var suspending by remember { mutableStateOf<Worker?>(null) }
    val pickCsv = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) scope.launch {
            val text = withContext(Dispatchers.IO) {
                context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
            }
            if (text != null) viewModel.import(text)
        }
    }
    val business = state.data?.business
    val canEdit = business?.canPrepare == true
    val canApprove = business?.canApprove == true
    Scaffold(
        topBar = {
            val subtitle = state.data?.let {
                "${it.active.size} on payroll · ${money(it.monthlyPayroll, it.active.firstOrNull()?.currency ?: "")} a month"
            }
            BackTopBar("Workers", subtitle, onBack) {
                if (canApprove) IconButton(onClick = { showJoinCode = true }) { Icon(Icons.Outlined.QrCode2, "Join code") }
                if (canEdit) IconButton(onClick = { pickCsv.launch("text/*") }) { Icon(Icons.Outlined.UploadFile, "Invite workers from a CSV file") }
            }
        },
        floatingActionButton = {
            if (canEdit) ExtendedFloatingActionButton(onClick = { inviting = true }, icon = { Icon(Icons.Outlined.PersonAdd, null) },
                text = { Text("Invite worker") })
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { data ->
            item {
                ScrollableTabRow(selectedTabIndex = data.tab.ordinal, edgePadding = 0.dp) {
                    WorkerTab.entries.forEach { tab ->
                        val count = data.count(tab)
                        Tab(selected = tab == data.tab, onClick = { viewModel.showTab(tab) },
                            text = { Text(if (count > 0) "${tab.label} ($count)" else tab.label) })
                    }
                }
            }
            item {
                FluxTextField(value = data.search, onValueChange = viewModel::search, label = "Search name, phone, job or account")
            }
            if (data.shown.isEmpty()) {
                item {
                    val (title, text) = when (data.tab) {
                        WorkerTab.ACTIVE -> "No workers yet" to
                            "Invite workers by phone number or FluxPay account number. They join when they accept, and their pay goes to their own wallet."
                        WorkerTab.INVITED -> "No pending invitations" to "Invitations you send appear here until the worker accepts."
                        WorkerTab.REQUESTS -> "No requests to join" to
                            "Workers who enter or scan your join code ask to join here. Nobody joins without your approval."
                        WorkerTab.SUSPENDED -> "Nobody is suspended" to "Suspended workers stay on the register but can't be paid."
                    }
                    EmptyState(Icons.Outlined.Badge, title, text)
                }
            }
            items(data.shown, key = { it.id }) { worker ->
                WorkerRow(
                    worker = worker,
                    canEdit = canEdit,
                    canApprove = canApprove,
                    onChangeSalary = { editing = worker },
                    onSuspend = { suspending = worker },
                    onReactivate = { viewModel.reactivate(worker) },
                    onRemove = { removing = worker },
                    onResend = { viewModel.resend(worker) },
                    onApprove = { approving = worker },
                    onDecline = { declining = worker },
                )
                HorizontalDivider()
            }
        }
    }
    if (inviting) {
        InputDialog(
            title = "Invite worker",
            message = "They get a code by SMS (and email) and join when they accept it. They create their own " +
                "FluxPay login: you never see or set their password.",
            fields = listOf(
                Triple("Phone number or FluxPay account number", KeyboardType.Phone, ""),
                Triple("Full name", KeyboardType.Text, ""),
                Triple("Email (optional)", KeyboardType.Email, ""),
                Triple("Monthly salary", KeyboardType.Decimal, ""),
                Triple("Job title (optional)", KeyboardType.Text, ""),
            ),
            confirm = "Send invitation",
            onConfirm = { (who, name, email, salary, job) -> inviting = false; viewModel.invite(name, who, email, salary, job) },
            onDismiss = { inviting = false },
        )
    }
    editing?.let { worker ->
        InputDialog("Change salary", worker.name,
            listOf(Triple("Monthly salary", KeyboardType.Decimal, worker.salary?.toPlainString().orEmpty())),
            "Save", onConfirm = { (salary) -> editing = null; viewModel.changeSalary(worker, salary) }, onDismiss = { editing = null })
    }
    removing?.let { worker ->
        val invite = worker.status == WorkerStatus.INVITED
        InputDialog(
            if (invite) "Cancel the invitation to ${worker.name}?" else "Remove ${worker.name}?",
            if (invite) "Their code stops working." else "They won't be in future pay runs. Past payslips stay on record, and their FluxPay account stays theirs.",
            emptyList(), if (invite) "Cancel invitation" else "Remove",
            onConfirm = { removing = null; viewModel.remove(worker) }, onDismiss = { removing = null }, destructive = true,
        )
    }
    approving?.let { worker ->
        InputDialog(
            "Approve ${worker.name}?",
            "They asked to join with your join code${worker.phoneNumber.takeIf { it.isNotBlank() }?.let { " (phone $it)" } ?: ""}. " +
                "Make sure you know them: once approved they can be paid from your business account.",
            listOf(Triple("Monthly salary", KeyboardType.Decimal, ""), Triple("Job title (optional)", KeyboardType.Text, worker.jobTitle)),
            "Approve", onConfirm = { (salary, job) -> approving = null; viewModel.approve(worker, salary, job) },
            onDismiss = { approving = null },
        )
    }
    declining?.let { worker ->
        InputDialog("Decline ${worker.name}?", "They won't be added. They can ask again only with a valid join code.",
            listOf(Triple("Reason (optional)", KeyboardType.Text, "")), "Decline", requireFirst = false, destructive = true,
            onConfirm = { (reason) -> declining = null; viewModel.decline(worker, reason) }, onDismiss = { declining = null })
    }
    suspending?.let { worker ->
        InputDialog("Suspend ${worker.name}?", "They stay on the register but can't be paid until you reactivate them.",
            listOf(Triple("Reason", KeyboardType.Text, "")), "Suspend", destructive = true,
            onConfirm = { (reason) -> suspending = null; viewModel.suspend(worker, reason) }, onDismiss = { suspending = null })
    }
    if (showJoinCode) {
        JoinCodeDialog(
            code = state.data?.joinCode,
            onNewCode = { viewModel.setJoinCode(true) },
            onTurnOff = { viewModel.setJoinCode(false) },
            onDismiss = { showJoinCode = false },
        )
    }
}

@Composable
private fun WorkerRow(
    worker: Worker,
    canEdit: Boolean,
    canApprove: Boolean,
    onChangeSalary: () -> Unit,
    onSuspend: () -> Unit,
    onReactivate: () -> Unit,
    onRemove: () -> Unit,
    onResend: () -> Unit,
    onApprove: () -> Unit,
    onDecline: () -> Unit,
) {
    var menu by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Avatar(worker.name, size = 40)
            Column(Modifier.weight(1f)) {
                Text(worker.name, style = MaterialTheme.typography.bodyLarge)
                val detail = when (worker.status) {
                    WorkerStatus.INVITED -> listOf("Invited", worker.phoneNumber)
                    WorkerStatus.PENDING_ACTIVATION -> listOf("Wants to join", worker.phoneNumber)
                    WorkerStatus.SUSPENDED -> listOf(worker.statusNote.ifBlank { "Suspended" })
                    else -> listOf(worker.jobTitle, worker.accountNumber)
                }
                Text(detail.filter { it.isNotBlank() }.joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Column(horizontalAlignment = Alignment.End) {
                worker.salary?.let { Text(money(it, worker.currency), style = MaterialTheme.typography.bodyMedium) }
                if (worker.status != WorkerStatus.ACTIVE) StatusPill(worker.statusLabel, workerTone(worker.status))
            }
            if (canEdit && worker.status in setOf(WorkerStatus.ACTIVE, WorkerStatus.SUSPENDED)) {
                Column {
                    TextButton(onClick = { menu = true }) { Text("Manage") }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(text = { Text("Change salary") }, onClick = { menu = false; onChangeSalary() })
                        if (worker.status == WorkerStatus.ACTIVE) {
                            DropdownMenuItem(text = { Text("Suspend") }, onClick = { menu = false; onSuspend() })
                        } else {
                            DropdownMenuItem(text = { Text("Reactivate") }, onClick = { menu = false; onReactivate() })
                        }
                        DropdownMenuItem(text = { Text("Remove from payroll") }, onClick = { menu = false; onRemove() })
                    }
                }
            }
        }
        // Waiting on someone: the next step is right on the row.
        when (worker.status) {
            WorkerStatus.INVITED -> if (canEdit) Row(Modifier.padding(start = 52.dp)) {
                TextButton(onClick = onResend) { Text("Resend") }
                TextButton(onClick = onRemove) { Text("Cancel invitation", color = MaterialTheme.colorScheme.error) }
            }
            WorkerStatus.PENDING_ACTIVATION -> Row(Modifier.padding(start = 52.dp)) {
                if (canApprove) {
                    TextButton(onClick = onApprove) { Text("Approve") }
                    TextButton(onClick = onDecline) { Text("Reject", color = MaterialTheme.colorScheme.error) }
                } else {
                    Text("An owner or admin approves requests.", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            else -> Unit
        }
    }
}

/** The business's join code: workers scan the QR code or type the code, then someone approves them. */
@Composable
private fun JoinCodeDialog(code: JoinCode?, onNewCode: () -> Unit, onTurnOff: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Join code") },
        text = {
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                val text = code?.code
                val link = code?.link
                if (code?.enabled == true && text != null && link != null) {
                    QrImage(link, Modifier.size(220.dp))
                    Text(text, style = MaterialTheme.typography.headlineSmall, fontFamily = FontFamily.Monospace,
                        fontWeight = FontWeight.SemiBold)
                    Text("Workers open FluxPay, choose Join a business, and scan this or type the code. You approve each " +
                        "request under Requests. Only share it with people who work for you.",
                        style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center)
                } else {
                    Text("Turn on a join code so workers who already use FluxPay can ask to join. Nobody joins without " +
                        "approval, and nobody can find your business by its name.", style = MaterialTheme.typography.bodyMedium)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onNewCode) { Text(if (code?.enabled == true) "New code" else "Turn on") }
        },
        dismissButton = {
            Row {
                if (code?.enabled == true) TextButton(onClick = onTurnOff) { Text("Turn off", color = MaterialTheme.colorScheme.error) }
                TextButton(onClick = onDismiss) { Text("Close") }
            }
        },
    )
}

@Composable
private fun QrImage(content: String, modifier: Modifier = Modifier) {
    val bitmap = remember(content) {
        val matrix = QRCodeWriter().encode(content, BarcodeFormat.QR_CODE, 512, 512)
        Bitmap.createBitmap(matrix.width, matrix.height, Bitmap.Config.RGB_565).apply {
            for (x in 0 until matrix.width) for (y in 0 until matrix.height) {
                setPixel(x, y, if (matrix[x, y]) android.graphics.Color.BLACK else android.graphics.Color.WHITE)
            }
        }.asImageBitmap()
    }
    Image(bitmap, contentDescription = "QR code to join this business", modifier = modifier)
}

// --- The worker's side ----------------------------------------------------------------------------

private fun employerText(employer: Employer) = when (employer.status) {
    WorkerStatus.ACTIVE -> "You're paid into your own FluxPay wallet."
    WorkerStatus.PENDING_ACTIVATION -> "You asked to join. Waiting for the business to approve you."
    WorkerStatus.INVITED -> "You're invited. Enter the code from your SMS or email under Join a business."
    WorkerStatus.SUSPENDED -> "The business has paused paying you."
    else -> employer.statusLabel
}

/** The businesses the user works for (or asked to join, or is invited to), and leaving one. */
@Composable
fun EmployersScreen(onBack: () -> Unit, onJoin: () -> Unit, viewModel: EmployersViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var leaving by remember { mutableStateOf<Employer?>(null) }
    Scaffold(
        topBar = { BackTopBar("My employers", "Businesses that pay you through FluxPay", onBack) },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = onJoin, icon = { Icon(Icons.Outlined.QrCodeScanner, null) },
                text = { Text("Join a business") })
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { employers ->
            if (employers.isEmpty()) {
                item {
                    EmptyState(Icons.Outlined.Storefront, "No employers yet",
                        "If you work for a business that pays through FluxPay, join it with the code from your invitation " +
                            "or by scanning its QR code.")
                }
            }
            items(employers, key = { it.id }) { employer ->
                Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Avatar(employer.business, size = 40)
                            Column(Modifier.weight(1f)) {
                                Text(employer.business, style = MaterialTheme.typography.titleMedium)
                                if (employer.jobTitle.isNotBlank()) {
                                    Text(employer.jobTitle, style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                            StatusPill(employer.statusLabel, workerTone(employer.status))
                        }
                        Text(employerText(employer), style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = { leaving = employer }, modifier = Modifier.align(Alignment.End)) {
                            Text(
                                when (employer.status) {
                                    WorkerStatus.PENDING_ACTIVATION -> "Cancel request"
                                    WorkerStatus.INVITED -> "Decline"
                                    else -> "Leave"
                                },
                                color = MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                }
            }
        }
    }
    leaving?.let { employer ->
        InputDialog(
            "Leave ${employer.business}?",
            "They won't be able to pay you any more. Your FluxPay account, balance and past payslips stay yours.",
            emptyList(), "Leave", destructive = true,
            onConfirm = { leaving = null; viewModel.leave(employer) }, onDismiss = { leaving = null },
        )
    }
}

/**
 * Joining a business: type the code from an invitation (SMS/email) or a business's join code, or scan its QR code.
 * An invitation shows who it's from before accepting; a join code sends a request the business approves.
 */
@Composable
fun JoinBusinessScreen(onBack: () -> Unit, onDone: () -> Unit, viewModel: JoinBusinessViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current
    Scaffold(
        topBar = { BackTopBar("Join a business", "Get paid by your employer through FluxPay", onBack) },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, {}, viewModel::messageShown) { data ->
            val done = data.done
            val invitation = data.invitation
            when {
                done != null -> item {
                    val active = done.status == WorkerStatus.ACTIVE
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        EmptyState(
                            if (active) Icons.Outlined.CheckCircle else Icons.Outlined.HourglassTop,
                            if (active) "You work for ${done.business}" else "Request sent to ${done.business}",
                            if (active) "Your pay will go straight into your own FluxPay wallet. ${done.business} can't see your password or other money."
                            else "An owner or admin at ${done.business} will approve you. You'll see it under My employers.",
                        )
                        FluxPrimaryButton("Done", onDone)
                    }
                }
                invitation != null -> item {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text("${invitation.business} invited you", style = MaterialTheme.typography.titleMedium)
                                Text(listOf("as ${invitation.name}", invitation.jobTitle).filter { it.isNotBlank() }.joinToString(" · "),
                                    style = MaterialTheme.typography.bodyMedium)
                                Text("Accept to be paid by ${invitation.business} into your own FluxPay wallet. You can leave any time.",
                                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        FluxPrimaryButton("Accept", viewModel::accept, loading = state.busy)
                        FluxSecondaryButton("Not now", onBack)
                    }
                }
                else -> item {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text("Enter the code from your invitation SMS or email, or your employer's join code. " +
                            "Or scan the QR code your employer shows you.", style = MaterialTheme.typography.bodyMedium)
                        FluxTextField(value = data.code, onValueChange = viewModel::onCode, label = "Code, e.g. K7Q4M-9ZPXW",
                            onImeAction = viewModel::submit)
                        FluxPrimaryButton("Continue", viewModel::submit, enabled = data.code.isNotBlank(), loading = state.busy)
                        FluxSecondaryButton("Scan QR code", {
                            val options = GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
                            GmsBarcodeScanning.getClient(context, options).startScan()
                                .addOnSuccessListener { barcode -> barcode.rawValue?.let(viewModel::onScanned) }
                        })
                        Text("You join a business only with its code or its approval: nobody can add you, and you can't " +
                            "join a business just by its name.", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}
