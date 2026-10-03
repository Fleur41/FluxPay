package com.fluxpay.app.session

import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.util.Constants
import com.fluxpay.core.domain.usecase.LogoutUseCase
import com.fluxpay.core.domain.usecase.ObserveSessionUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch

/**
 * Secure session timeout built on Handler + Looper.
 *
 * - A dedicated [HandlerThread] (with its own [Looper]) ticks once a second, off the main thread.
 * - When the deadline passes, the logout is posted back to the main [Looper].
 * - Every user interaction (MainActivity.onUserInteraction) pushes the deadline forward.
 * - [onCleared] removes all pending callbacks and quits the thread so neither the
 *   Runnables nor the thread outlive this ViewModel (no leaks — LeakCanary stays quiet).
 *
 * [SystemClock.elapsedRealtime] keeps counting while the app is in the background, so
 * leaving FluxPay for 5 minutes also signs the user out.
 */
@HiltViewModel
class SessionTimeoutViewModel @Inject constructor(
    observeSession: ObserveSessionUseCase,
    private val logoutUseCase: LogoutUseCase,
) : ViewModel() {

    private val timerThread = HandlerThread("fluxpay-session-timer").apply { start() }
    private val timerHandler = Handler(timerThread.looper)
    private val mainHandler = Handler(Looper.getMainLooper())

    @Volatile private var deadline = 0L
    @Volatile private var active = false

    /** Seconds left while the "still there?" warning should show, otherwise null. */
    private val _warningSecondsLeft = MutableStateFlow<Long?>(null)
    val warningSecondsLeft: StateFlow<Long?> = _warningSecondsLeft.asStateFlow()

    private val _timedOut = MutableStateFlow(false)
    val timedOut: StateFlow<Boolean> = _timedOut.asStateFlow()

    private val tick = object : Runnable {
        override fun run() {
            if (!active) return
            val remaining = deadline - SystemClock.elapsedRealtime()
            if (remaining <= 0) {
                mainHandler.post { expire() }
                return
            }
            _warningSecondsLeft.value =
                if (remaining <= Constants.SESSION_WARNING_MS) (remaining + 999) / 1000 else null
            timerHandler.postDelayed(this, TICK_MS)
        }
    }

    init {
        observeSession()
            .onEach { loggedIn -> if (loggedIn) start() else stop() }
            .launchIn(viewModelScope)
    }

    /** Called on the main thread for every touch/key event. */
    fun onUserInteraction() {
        if (active) deadline = SystemClock.elapsedRealtime() + Constants.SESSION_TIMEOUT_MS
    }

    fun staySignedIn() = onUserInteraction()

    fun onTimeoutMessageShown() {
        _timedOut.value = false
    }

    private fun start() {
        if (active) return
        active = true
        _timedOut.value = false
        deadline = SystemClock.elapsedRealtime() + Constants.SESSION_TIMEOUT_MS
        timerHandler.removeCallbacks(tick)
        timerHandler.post(tick)
    }

    private fun stop() {
        active = false
        timerHandler.removeCallbacks(tick)
        _warningSecondsLeft.value = null
    }

    private fun expire() {
        if (!active) return
        stop()
        _timedOut.value = true
        viewModelScope.launch { logoutUseCase(revokeRemotely = true) }
    }

    override fun onCleared() {
        active = false
        timerHandler.removeCallbacksAndMessages(null)
        mainHandler.removeCallbacksAndMessages(null)
        timerThread.quitSafely()
        super.onCleared()
    }

    private companion object {
        const val TICK_MS = 1_000L
    }
}
