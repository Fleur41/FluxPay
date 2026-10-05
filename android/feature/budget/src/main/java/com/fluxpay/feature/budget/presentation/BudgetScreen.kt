package com.fluxpay.feature.budget.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Calculate
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.FullScreenLoading
import com.fluxpay.feature.budget.presentation.components.GuidelineCard
import com.fluxpay.feature.budget.presentation.components.KindSection
import com.fluxpay.feature.budget.presentation.components.LineEditorDialog
import com.fluxpay.feature.budget.presentation.components.MonthSpendingCard
import com.fluxpay.feature.budget.presentation.components.SummaryCard
import com.fluxpay.feature.budget.presentation.viewmodel.BudgetViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BudgetScreen(
    onBack: () -> Unit, viewModel:
    BudgetViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Budget planner") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        val summary = state.summary
        if (!state.isLoaded || summary == null) {
            FullScreenLoading(Modifier.padding(padding))
            return@Scaffold
        }
        LazyColumn(
            Modifier.padding(padding).fillMaxSize(),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            if (state.isEmpty) {
                item(key = "intro") {
                    EmptyState(
                        Icons.Outlined.Calculate,
                        "Plan your month",
                        "Add your income, then what goes to needs, wants and savings. Tap a suggestion to start.",
                    )
                }
            } else {
                item(key = "summary") { SummaryCard(summary, state.currency) }
                item(key = "month") { MonthSpendingCard(summary, state.currency) }
                if (summary.income.signum() > 0 && summary.guideline.isNotEmpty()) {
                    item(key = "guideline") { GuidelineCard(summary, state.currency) }
                }
            }
            BudgetKind.entries.forEach { kind ->
                item(key = kind.name) {
                    KindSection(
                        kind = kind,
                        lines = state.linesByKind[kind].orEmpty(),
                        currency = state.currency,
                        onAdd = { label -> viewModel.add(kind, label) },
                        onEdit = viewModel::edit,
                    )
                }
            }
        }
    }

    state.editor?.let { editor ->
        LineEditorDialog(
            state = editor,
            currency = state.currency,
            onLabelChange = viewModel::onLabelChange,
            onAmountChange = viewModel::onAmountChange,
            onKindChange = viewModel::onKindChange,
            onSave = viewModel::saveEditor,
            onDelete = viewModel::deleteEditorLine,
            onDismiss = viewModel::dismissEditor,
        )
    }
}
