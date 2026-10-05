package com.fluxpay.app

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.app.session.SessionTimeoutViewModel
import com.fluxpay.app.ui.FluxPayApp
import com.fluxpay.core.ui.theme.FluxPayTheme
import dagger.hilt.android.AndroidEntryPoint

/**
 * The only Activity. It hosts the Compose navigation graph and owns two activity-scoped
 * ViewModels: [MainViewModel] (session, theme, deep links) and [SessionTimeoutViewModel].
 *
 * It extends FragmentActivity (a ComponentActivity) because BiometricPrompt needs one.
 */
@AndroidEntryPoint
class MainActivity : FragmentActivity() {

    private val mainViewModel: MainViewModel by viewModels()
    private val sessionViewModel: SessionTimeoutViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        val splash = installSplashScreen()
        super.onCreate(savedInstanceState)
        splash.setKeepOnScreenCondition { mainViewModel.uiState.value is MainUiState.Loading }

        if (BuildConfig.SECURE_SCREEN) {
            // Balances must not appear in screenshots, screen recordings or the recents preview.
            window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        }
        enableEdgeToEdge()

        // On a fresh launch, take the deep link ourselves (instead of letting NavHost
        // auto-handle it) so a signed-out user is sent to login first.
        if (savedInstanceState == null) routeDeepLink(intent)

        setContent {
            val uiState by mainViewModel.uiState.collectAsStateWithLifecycle()
            val pendingDeepLink by mainViewModel.pendingDeepLink.collectAsStateWithLifecycle()
            val showBusinessTab by mainViewModel.showBusinessTab.collectAsStateWithLifecycle()
            val warningSeconds by sessionViewModel.warningSecondsLeft.collectAsStateWithLifecycle()
            val timedOutAfterMinutes by sessionViewModel.timedOutAfterMinutes.collectAsStateWithLifecycle()

            val ready = uiState as? MainUiState.Ready ?: return@setContent
            FluxPayTheme(themeMode = ready.themeMode) {
                FluxPayApp(
                    isLoggedIn = ready.isLoggedIn,
                    showBusinessTab = showBusinessTab,
                    pendingDeepLink = pendingDeepLink,
                    onDeepLinkConsumed = mainViewModel::onDeepLinkConsumed,
                    sessionWarningSeconds = warningSeconds,
                    onStaySignedIn = sessionViewModel::staySignedIn,
                    timedOutAfterMinutes = timedOutAfterMinutes,
                    onTimedOutShown = sessionViewModel::onTimeoutMessageShown,
                )
            }
        }
    }

    /** singleTop: deep links that arrive while we're already on top land here, not in a new instance. */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        routeDeepLink(intent)
    }

    /** Any touch or key press resets the inactivity timer. */
    override fun onUserInteraction() {
        super.onUserInteraction()
        sessionViewModel.onUserInteraction()
    }

    private fun routeDeepLink(intent: Intent?) {
        val link = intent?.data ?: return
        mainViewModel.onDeepLink(link.toString())
        intent.data = null // consumed: don't re-handle it after a configuration change
    }
}
