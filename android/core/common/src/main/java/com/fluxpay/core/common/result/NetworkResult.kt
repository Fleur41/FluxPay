package com.fluxpay.core.common.result

/**
 * Wraps every network-backed operation so the UI can render Loading / Success / Error
 * without try/catch blocks leaking into ViewModels.
 */
sealed interface NetworkResult<out T> {
    data class Success<T>(val data: T) : NetworkResult<T>

    data class Error(
        val message: String,
        /** Machine-readable code from the Django error envelope, e.g. "insufficient_funds". */
        val code: String? = null,
        val httpStatus: Int? = null,
        val cause: Throwable? = null,
    ) : NetworkResult<Nothing> {
        val isNetworkFailure: Boolean get() = httpStatus == null && code == ErrorCodes.NETWORK
        val isUnauthorized: Boolean get() = httpStatus == 401
    }

    data object Loading : NetworkResult<Nothing>
}

object ErrorCodes {
    const val NETWORK = "network_unavailable"
    const val UNKNOWN = "unknown"
}

inline fun <T, R> NetworkResult<T>.map(transform: (T) -> R): NetworkResult<R> = when (this) {
    is NetworkResult.Success -> NetworkResult.Success(transform(data))
    is NetworkResult.Error -> this
    NetworkResult.Loading -> NetworkResult.Loading
}

inline fun <T> NetworkResult<T>.onSuccess(action: (T) -> Unit): NetworkResult<T> {
    if (this is NetworkResult.Success) action(data)
    return this
}

inline fun <T> NetworkResult<T>.onError(action: (NetworkResult.Error) -> Unit): NetworkResult<T> {
    if (this is NetworkResult.Error) action(this)
    return this
}

fun <T> NetworkResult<T>.getOrNull(): T? = (this as? NetworkResult.Success)?.data
