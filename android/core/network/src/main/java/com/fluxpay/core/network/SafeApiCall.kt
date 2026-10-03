package com.fluxpay.core.network

import com.fluxpay.core.common.result.ErrorCodes
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.network.dto.ErrorEnvelopeDto
import com.squareup.moshi.Moshi
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.cancellation.CancellationException
import retrofit2.HttpException

/**
 * Runs a Retrofit call and converts every outcome into a [NetworkResult], parsing the
 * Django error envelope so the UI gets a human-readable message and a stable code.
 */
@Singleton
class ApiCaller @Inject constructor(moshi: Moshi) {

    private val errorAdapter = moshi.adapter(ErrorEnvelopeDto::class.java)

    suspend operator fun <T> invoke(block: suspend () -> T): NetworkResult<T> = try {
        NetworkResult.Success(block())
    } catch (e: CancellationException) {
        throw e // never swallow coroutine cancellation
    } catch (e: HttpException) {
        val envelope = runCatching { e.response()?.errorBody()?.string()?.let(errorAdapter::fromJson) }.getOrNull()
        NetworkResult.Error(
            message = envelope?.error?.message ?: defaultMessage(e.code()),
            code = envelope?.error?.code,
            httpStatus = e.code(),
            cause = e,
        )
    } catch (e: IOException) {
        NetworkResult.Error(
            message = "You're offline or the server can't be reached. Showing saved data.",
            code = ErrorCodes.NETWORK,
            cause = e,
        )
    } catch (e: Exception) {
        NetworkResult.Error(message = "Unexpected error: ${e.message}", code = ErrorCodes.UNKNOWN, cause = e)
    }

    private fun defaultMessage(code: Int) = when (code) {
        401 -> "Your session has expired. Please sign in again."
        403 -> "You don't have permission to do that."
        404 -> "Not found."
        429 -> "Too many attempts. Please wait a moment."
        in 500..599 -> "FluxPay is having trouble right now. Please try again shortly."
        else -> "Request failed ($code)."
    }
}
