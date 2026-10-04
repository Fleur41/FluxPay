package com.fluxpay.feature.budget.presentation.state

import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.feature.budget.domain.BudgetSummary

data class BudgetUiState(
    val isLoaded: Boolean = false,
    val currency: String = "",
    val linesByKind: Map<BudgetKind, List<BudgetLine>> = emptyMap(),
    val summary: BudgetSummary? = null,
    val editor: LineEditorState? = null,
) {
    val isEmpty: Boolean get() = linesByKind.values.all { it.isEmpty() }
}

/** The add/edit dialog. `id == 0` means a new line. */
data class LineEditorState(
    val id: Long = 0,
    val kind: BudgetKind,
    val label: String = "",
    val amount: String = "",
    val labelError: String? = null,
    val amountError: String? = null,
) {
    val isNew: Boolean get() = id == 0L
}
