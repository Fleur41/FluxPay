package com.fluxpay.feature.business.presentation

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.GroupAdd
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.Member
import com.fluxpay.core.domain.model.TeamInvitation
import com.fluxpay.core.domain.model.TeamRole
import com.fluxpay.core.ui.components.Avatar
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.core.ui.components.SectionTitle
import com.fluxpay.feature.business.presentation.components.BackTopBar
import com.fluxpay.feature.business.presentation.components.InputDialog
import com.fluxpay.feature.business.presentation.components.StatusPill
import com.fluxpay.feature.business.presentation.components.Tone
import com.fluxpay.feature.business.presentation.viewmodel.JoinTeamViewModel
import com.fluxpay.feature.business.presentation.viewmodel.NewBusinessViewModel
import com.fluxpay.feature.business.presentation.viewmodel.TeamViewModel

// --- Starting a business --------------------------------------------------------------------------

/** Anyone can start a business: they become its owner, and it gets its own wallet. */
@Composable
fun NewBusinessScreen(onBack: () -> Unit, onCreated: (String) -> Unit, viewModel: NewBusinessViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var name by remember { mutableStateOf("") }
    var registration by remember { mutableStateOf("") }
    LaunchedEffect(state.data?.createdId) { state.data?.createdId?.let(onCreated) }
    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); viewModel.messageShown() }
    }
    Scaffold(topBar = { BackTopBar("Start a business", null, onBack) }, snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        Column(
            Modifier.padding(padding).padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("You'll be its owner. It gets its own wallet, separate from yours, to pay workers and suppliers, " +
                "and its own books. You can invite others to help run it.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            FluxTextField(value = name, onValueChange = { name = it }, label = "Business name")
            FluxTextField(value = registration, onValueChange = { registration = it }, label = "Registration number (optional)",
                supportingText = "E.g. from the Business Registration Service. You can add it later.")
            FluxPrimaryButton("Create business", { viewModel.create(name, registration) }, enabled = name.isNotBlank(),
                loading = state.busy)
        }
    }
}

// --- The team -------------------------------------------------------------------------------------

private fun roleTone(role: String) = when (role) {
    "OWNER" -> Tone.GOOD
    "ADMIN" -> Tone.WAIT
    else -> Tone.QUIET
}

/**
 * Who helps run the business, and their roles. Owners and admins invite people by email and change roles;
 * admins manage finance and viewers only. Anyone can leave, except the last owner.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TeamScreen(onBack: () -> Unit, onLeft: () -> Unit, viewModel: TeamViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    var inviting by remember { mutableStateOf(false) }
    var selected by remember { mutableStateOf<Member?>(null) }
    var removing by remember { mutableStateOf<Member?>(null) }
    var cancelling by remember { mutableStateOf<TeamInvitation?>(null) }
    val team = state.data
    LaunchedEffect(team?.left) { if (team?.left == true) onLeft() }
    Scaffold(
        topBar = { BackTopBar("Team", team?.business?.name, onBack) },
        floatingActionButton = {
            if (team != null && team.business.manageableRoles.isNotEmpty()) {
                ExtendedFloatingActionButton(onClick = { inviting = true }, icon = { Icon(Icons.Outlined.GroupAdd, null) },
                    text = { Text("Invite") })
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        ScreenBody(state, snackbar, padding, viewModel::load, viewModel::messageShown) { data ->
            item {
                Text("People who run ${data.business.name} with you. Workers aren't here: they're only paid, under Workers.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            item { SectionTitle("Members") }
            items(data.members, key = { it.id }) { member ->
                val me = data.isMe(member)
                Row(
                    Modifier.fillMaxWidth().clickable(enabled = me || data.canManage(member.role)) { selected = member }
                        .padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Avatar(member.fullName.ifBlank { member.email }, size = 36)
                    Column(Modifier.weight(1f)) {
                        Text(member.fullName.ifBlank { member.email } + if (me) " (you)" else "")
                        Text(member.email, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    StatusPill(member.roleLabel, roleTone(member.role))
                }
                HorizontalDivider()
            }
            if (data.invitations.isNotEmpty()) {
                item { SectionTitle("Waiting to accept", Modifier.padding(top = 8.dp)) }
                items(data.invitations, key = { it.id }) { invitation ->
                    Row(
                        Modifier.fillMaxWidth().clickable(enabled = data.canManage(invitation.role)) { cancelling = invitation }
                            .padding(vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(invitation.email)
                            Text("Invited by ${invitation.invitedBy} · link expires ${invitation.expiresAt}",
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        StatusPill(invitation.roleLabel, Tone.WAIT)
                    }
                    HorizontalDivider()
                }
            }
        }
    }
    if (inviting && team != null) {
        InviteMemberDialog(team.business.manageableRoles, onInvite = { email, role -> inviting = false; viewModel.invite(email, role) },
            onDismiss = { inviting = false })
    }
    selected?.let { member ->
        val me = team?.isMe(member) == true
        ModalBottomSheet(onDismissRequest = { selected = null }) {
            Column(Modifier.padding(horizontal = 16.dp).padding(bottom = 32.dp)) {
                Text(member.fullName.ifBlank { member.email }, style = MaterialTheme.typography.titleMedium)
                Text("${member.roleLabel} · ${member.email}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                if (me) {
                    Text("You can't change your own role: ask another owner.", Modifier.padding(top = 12.dp),
                        style = MaterialTheme.typography.bodySmall)
                    TextButton(onClick = { selected = null; removing = member }, Modifier.fillMaxWidth()) {
                        Text("Leave ${team?.business?.name}", Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.error)
                    }
                } else {
                    Text("Change role", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.titleSmall)
                    team?.business?.manageableRoles.orEmpty().forEach { role ->
                        TextButton(onClick = { selected = null; viewModel.changeRole(member, role) }, Modifier.fillMaxWidth()) {
                            Column(Modifier.fillMaxWidth()) {
                                Text(role.label + if (role.name == member.role) "  ✓" else "")
                                Text(role.description, style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                    HorizontalDivider(Modifier.padding(vertical = 8.dp))
                    TextButton(onClick = { selected = null; removing = member }, Modifier.fillMaxWidth()) {
                        Text("Remove from the team", Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        }
    }
    removing?.let { member ->
        val me = team?.isMe(member) == true
        InputDialog(
            if (me) "Leave ${team?.business?.name}?" else "Remove ${member.fullName.ifBlank { member.email }}?",
            if (me) "You'll no longer see this business. An owner or admin can invite you back."
            else "They'll no longer see this business. Their past actions stay in the audit log.",
            emptyList(), if (me) "Leave" else "Remove",
            onConfirm = { removing = null; if (me) viewModel.leave(member) else viewModel.remove(member) },
            onDismiss = { removing = null }, destructive = true,
        )
    }
    cancelling?.let { invitation ->
        InputDialog("Cancel the invitation to ${invitation.email}?", "The link in their email stops working.", emptyList(),
            "Cancel invitation", onConfirm = { cancelling = null; viewModel.cancelInvitation(invitation) },
            onDismiss = { cancelling = null }, destructive = true)
    }
}

@Composable
private fun InviteMemberDialog(roles: List<TeamRole>, onInvite: (String, TeamRole) -> Unit, onDismiss: () -> Unit) {
    var email by remember { mutableStateOf("") }
    var role by remember { mutableStateOf(roles.firstOrNull { it == TeamRole.FINANCE } ?: roles.first()) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Invite to the team") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("They get an email with a link. They join once they open it in the FluxPay app, signed in with that email.",
                    style = MaterialTheme.typography.bodyMedium)
                FluxTextField(value = email, onValueChange = { email = it }, label = "Email", keyboardType = KeyboardType.Email)
                roles.forEach { option ->
                    Row(
                        Modifier.fillMaxWidth().selectable(option == role, role = Role.RadioButton) { role = option },
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = option == role, onClick = null)
                        Column(Modifier.padding(start = 8.dp)) {
                            Text(option.label)
                            Text(option.description, style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onInvite(email, role) }, enabled = email.contains("@")) { Text("Send invitation") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

// --- Accepting a team invitation ------------------------------------------------------------------

/** Opened from the invitation email's link, or with that link pasted in. */
@Composable
fun JoinTeamScreen(onBack: () -> Unit, onJoined: (String) -> Unit, viewModel: JoinTeamViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(state.data?.joined) { state.data?.joined?.let { onJoined(it.id) } }
    LaunchedEffect(state.message) {
        state.message?.let { snackbar.showSnackbar(it); viewModel.messageShown() }
    }
    Scaffold(topBar = { BackTopBar("Join a business team", null, onBack) }, snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        Column(
            Modifier.padding(padding).padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("A business invited you to help run it on FluxPay. Accept to see it under the Business tab. " +
                "You must be signed in with the email the invitation was sent to.",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            FluxTextField(value = state.data?.link.orEmpty(), onValueChange = viewModel::onLink, label = "Invitation link",
                supportingText = "Filled in when you open the link from the email. Or copy the link from the email and paste it here.",
                singleLine = false)
            FluxPrimaryButton("Accept invitation", viewModel::accept, enabled = !state.data?.link.isNullOrBlank(),
                loading = state.busy)
        }
    }
}
