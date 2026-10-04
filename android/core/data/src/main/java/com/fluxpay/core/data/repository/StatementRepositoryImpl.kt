package com.fluxpay.core.data.repository

import android.content.Context
import com.fluxpay.core.common.dispatcher.Dispatcher
import com.fluxpay.core.common.dispatcher.FluxDispatcher
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.DownloadedStatement
import com.fluxpay.core.domain.model.StatementFormat
import com.fluxpay.core.domain.model.StatementPeriod
import com.fluxpay.core.domain.repository.StatementRepository
import com.fluxpay.core.network.ApiCaller
import com.fluxpay.core.network.api.FluxPayApi
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext
import retrofit2.HttpException

/**
 * Statements are saved in the app's private cache (cache/statements/), which the app's FileProvider
 * exposes for opening and sharing. They hold financial data, so sign-out deletes them.
 */
@Singleton
class StatementRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: FluxPayApi,
    private val apiCaller: ApiCaller,
    @Dispatcher(FluxDispatcher.IO) private val io: CoroutineDispatcher,
) : StatementRepository {

    private val directory get() = File(context.cacheDir, DIRECTORY)

    override suspend fun download(period: StatementPeriod, format: StatementFormat): NetworkResult<DownloadedStatement> =
        withContext(io) {
            apiCaller {
                val response = api.statement(period.from.toString(), period.to.toString(), format.extension)
                if (!response.isSuccessful) throw HttpException(response) // ApiCaller reads the error envelope
                val body = response.body() ?: throw IOException("The server sent an empty statement.")
                val name = fileName(response.headers()["Content-Disposition"])
                    ?: "FluxPay-statement-${period.from}-to-${period.to}.${format.extension}"

                directory.mkdirs()
                val target = File(directory, name)
                val partial = File(directory, "$name.part") // never leave half a file under the real name
                body.use { partial.outputStream().use { out -> it.byteStream().copyTo(out) } }
                if (!partial.renameTo(target)) throw IOException("Couldn't save the statement.")
                DownloadedStatement(file = target, fileName = name, format = format)
            }
        }

    override suspend fun clearDownloads() {
        withContext(io) { directory.deleteRecursively() }
    }

    private companion object {
        const val DIRECTORY = "statements"
        private val FILENAME = Regex("""filename="([^"]+)"""")

        /** The server's file name, reduced to safe characters (it becomes a path on this phone). */
        fun fileName(contentDisposition: String?): String? = contentDisposition
            ?.let { FILENAME.find(it)?.groupValues?.get(1) }
            ?.replace(Regex("[^A-Za-z0-9._-]"), "_")
            ?.takeIf { it.isNotBlank() && !it.startsWith(".") }
    }
}
