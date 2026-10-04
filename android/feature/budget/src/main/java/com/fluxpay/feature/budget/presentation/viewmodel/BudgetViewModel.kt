package com.fluxpay.feature.budget.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.domain.model.BudgetKind
import com.fluxpay.core.domain.model.BudgetLine
import com.fluxpay.feature.budget.domain.usecase.DeleteBudgetLineUseCase
import com.fluxpay.feature.budget.domain.usecase.ObserveBudgetUseCase
import com.fluxpay.feature.budget.domain.usecase.SaveBudgetLineUseCase
import com.fluxpay.feature.budget.domain.usecase.SaveResult
import com.fluxpay.feature.budget.presentation.state.BudgetUiState
import com.fluxpay.feature.budget.presentation.state.LineEditorState
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@HiltViewModel
class BudgetViewModel @Inject constructor(
    observeBudget: ObserveBudgetUseCase,
    private val saveLine: SaveBudgetLineUseCase,
    private val deleteLine: DeleteBudgetLineUseCase,
) : ViewModel() {

    private val editor = MutableStateFlow<LineEditorState?>(null)

    val state: StateFlow<BudgetUiState> = combine(observeBudget(), editor) { snapshot, editorState ->
        BudgetUiState(
            isLoaded = snapshot.currency != null, // amounts need a currency to be shown in
            currency = snapshot.currency.orEmpty(),
            linesByKind = BudgetKind.entries.associateWith { kind -> snapshot.lines.filter { it.kind == kind } },
            summary = snapshot.summary,
            editor = editorState,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), BudgetUiState())

    fun add(kind: BudgetKind, label: String = "") {
        editor.value = LineEditorState(kind = kind, label = label)
    }

    fun edit(line: BudgetLine) {
        editor.value = LineEditorState(
            id = line.id,
            kind = line.kind,
            label = line.label,
            amount = line.amount.stripTrailingZeros().toPlainString(),
        )
    }

    fun onLabelChange(value: String) = editor.update { it?.copy(label = value, labelError = null) }

    fun onAmountChange(value: String) = editor.update { it?.copy(amount = value, amountError = null) }

    fun onKindChange(kind: BudgetKind) = editor.update { it?.copy(kind = kind) }

    fun dismissEditor() {
        editor.value = null
    }

    fun saveEditor() {
        val current = editor.value ?: return
        viewModelScope.launch {
            when (val result = saveLine(current.id, current.label, MoneyFormatter.parse(current.amount), current.kind)) {
                SaveResult.Saved -> editor.value = null
                is SaveResult.Invalid -> editor.update {
                    it?.copy(labelError = result.labelError, amountError = result.amountError)
                }
            }
        }
    }

    fun deleteEditorLine() {
        val current = editor.value ?: return
        if (current.isNew) return
        viewModelScope.launch {
            deleteLine(current.id)
            editor.value = null
        }
    }
}
