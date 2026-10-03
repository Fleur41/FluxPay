package com.fluxpay.app

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/** Hilt's dependency graph is rooted here. */
@HiltAndroidApp
class FluxPayApplication : Application()
