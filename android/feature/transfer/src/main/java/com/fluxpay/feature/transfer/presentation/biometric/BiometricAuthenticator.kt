package com.fluxpay.feature.transfer.presentation.biometric

import android.content.Context
import android.content.ContextWrapper
import android.os.Build
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

/**
 * Wraps BiometricPrompt. Every transfer must pass a fingerprint/face check or the device
 * PIN/pattern (DEVICE_CREDENTIAL) before the request is sent.
 *
 * The activity is only used for the duration of the call and never stored, so nothing leaks.
 */
object BiometricAuthenticator {

    sealed interface Availability {
        data object Available : Availability
        data class Unavailable(val reason: String) : Availability
    }

    // BIOMETRIC_STRONG + DEVICE_CREDENTIAL is only a supported combination on API 30+.
    private val allowedAuthenticators: Int
        get() = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            BIOMETRIC_STRONG or DEVICE_CREDENTIAL
        } else {
            BIOMETRIC_WEAK or DEVICE_CREDENTIAL
        }

    fun availability(context: Context): Availability =
        when (BiometricManager.from(context).canAuthenticate(allowedAuthenticators)) {
            BiometricManager.BIOMETRIC_SUCCESS -> Availability.Available
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED ->
                Availability.Unavailable("Set up a fingerprint, face unlock or screen lock to send money.")
            BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE,
            BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE,
            -> Availability.Unavailable("Set up a screen lock (PIN, pattern or password) to send money.")
            else -> Availability.Unavailable("Secure authentication isn't available on this device right now.")
        }

    fun authenticate(
        activity: FragmentActivity,
        title: String,
        subtitle: String,
        onSuccess: () -> Unit,
        onError: (String) -> Unit,
    ) {
        val prompt = BiometricPrompt(
            activity,
            ContextCompat.getMainExecutor(activity),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onSuccess()

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    val cancelled = errorCode == BiometricPrompt.ERROR_USER_CANCELED ||
                        errorCode == BiometricPrompt.ERROR_NEGATIVE_BUTTON ||
                        errorCode == BiometricPrompt.ERROR_CANCELED
                    if (!cancelled) onError(errString.toString())
                }
                // onAuthenticationFailed (a non-matching finger) is handled by the system prompt itself.
            },
        )
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title)
            .setSubtitle(subtitle)
            .setAllowedAuthenticators(allowedAuthenticators)
            .setConfirmationRequired(true)
            .build()
        prompt.authenticate(info)
    }
}

/** Compose's LocalContext may be a ContextWrapper; walk up to the hosting activity. */
tailrec fun Context.findFragmentActivity(): FragmentActivity? = when (this) {
    is FragmentActivity -> this
    is ContextWrapper -> baseContext.findFragmentActivity()
    else -> null
}
