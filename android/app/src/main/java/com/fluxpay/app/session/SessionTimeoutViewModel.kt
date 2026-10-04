package com.fluxpay.app.session

import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.domain.usecase.LogoutUseCase
import com.fluxpay.core.domain.usecase.ObservePlatformConfigUseCase
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
 * leaving FluxPay also counts as inactivity.
 *
 * The timeout comes from the server's platform settings (staff set it in admin). The timer is armed
 * once those rules are known; the app fetches them at start-up and caches them, so a signed-in user
 * always has them.
 */
@HiltViewModel
class SessionTimeoutViewModel @Inject constructor(
    observeSession: ObserveSessionUseCase,
    observeConfig: ObservePlatformConfigUseCase,
    private val logoutUseCase: LogoutUseCase,
) : ViewModel() {

    private val timerThread = HandlerThread("fluxpay-session-timer").apply { start() }
    private val timerHandler = Handler(timerThread.looper)
    private val mainHandler = Handler(Looper.getMainLooper())

    /** 0 while not armed (rules not loaded yet). */
    @Volatile private var deadline = 0L
    @Volatile private var active = false
    @Volatile private var timeoutMs: Long? = null
    @Volatile private var timeoutMinutes: Int? = null

    /** Seconds left while the "still there?" warning should show, otherwise null. */
    private val _warningSecondsLeft = MutableStateFlow<Long?>(null)
    val warningSecondsLeft: StateFlow<Long?> = _warningSecondsLeft.asStateFlow()

    /** The configured minutes once the session has timed out (for the message), otherwise null. */
    private val _timedOutAfterMinutes = MutableStateFlow<Int?>(null)
    val timedOutAfterMinutes: StateFlow<Int?> = _timedOutAfterMinutes.asStateFlow()

    private val tick = object : Runnable {
        override fun run() {
            if (!active) return
            if (deadline == 0L) { // not armed yet: wait for the rules
                timerHandler.postDelayed(this, TICK_MS)
                return
            }
            val remaining = deadline - SystemClock.elapsedRealtime()
            if (remaining <= 0) {
                mainHandler.post { expire() }
                return
            }
            _warningSecondsLeft.value =
                if (remaining <= warningMs()) (remaining + 999) / 1000 else null
            timerHandler.postDelayed(this, TICK_MS)
        }
    }

    init {
        observeConfig()
            .onEach { config ->
                timeoutMinutes = config?.sessionTimeoutMinutes
                timeoutMs = config?.sessionTimeoutMinutes?.let { it * 60_000L }
                if (active && deadline == 0L) arm()
            }
            .launchIn(viewModelScope)
        observeSession()
            .onEach { loggedIn -> if (loggedIn) start() else stop() }
            .launchIn(viewModelScope)
    }

    /** Called on the main thread for every touch/key event. */
    fun onUserInteraction() {
        if (active) arm()
    }

    fun staySignedIn() = onUserInteraction()

    fun onTimeoutMessageShown() {
        _timedOutAfterMinutes.value = null
    }

    private fun start() {
        if (active) return
        active = true
        _timedOutAfterMinutes.value = null
        deadline = 0L
        arm()
        timerHandler.removeCallbacks(tick)
        timerHandler.post(tick)
    }

    private fun stop() {
        active = false
        timerHandler.removeCallbacks(tick)
        _warningSecondsLeft.value = null
    }

    private fun arm() {
        deadline = timeoutMs?.let { SystemClock.elapsedRealtime() + it } ?: 0L
    }

    /** The "still there?" countdown: the last 30 seconds, or half the timeout if that is shorter. */
    private fun warningMs(): Long = minOf(WARNING_MS, (timeoutMs ?: 0L) / 2)

    private fun expire() {
        if (!active) return
        stop()
        _timedOutAfterMinutes.value = timeoutMinutes
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
        const val WARNING_MS = 30_000L // presentation only: how long the countdown banner shows
    }
}
