import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

// Release signing comes from keystore.properties (git-ignored). Without it, release
// builds fall back to the debug key so CI and local `assembleRelease` still work.
val keystorePropertiesFile = rootProject.file("keystore.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.exists()) keystorePropertiesFile.inputStream().use { load(it) }
}
val hasReleaseKeystore = keystorePropertiesFile.exists()

// API hosts and version can be overridden without editing code: ./gradlew -Pfluxpay.stagingUrl=https://...
fun propertyOr(property: String, default: String): String =
    (project.findProperty(property) as String?)?.takeIf { it.isNotBlank() } ?: default

android {
    namespace = "com.fluxpay.app"
    compileSdk = libs.versions.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "com.fluxpay.app"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.targetSdk.get().toInt()
        // The release workflow sets these from the git tag: -Pfluxpay.versionCode=10001 -Pfluxpay.versionName=1.0.1
        versionCode = propertyOr("fluxpay.versionCode", "1").toInt()
        versionName = propertyOr("fluxpay.versionName", "1.0.0")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables { useSupportLibrary = true }
    }

    signingConfigs {
        create("release") {
            if (hasReleaseKeystore) {
                storeFile = rootProject.file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    flavorDimensions += "environment"
    productFlavors {
        create("dev") {
            dimension = "environment"
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            // 10.0.2.2 is your computer's localhost as seen from the Android emulator.
            buildConfigField("String", "BASE_URL", "\"${propertyOr("fluxpay.devUrl", "http://10.0.2.2:8000/")}\"")
            buildConfigField("boolean", "ENABLE_LOGGING", "true")
            buildConfigField("boolean", "SECURE_SCREEN", "false")
            resValue("string", "app_name", "FluxPay Dev")
        }
        create("staging") {
            dimension = "environment"
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
            buildConfigField("String", "BASE_URL", "\"${propertyOr("fluxpay.stagingUrl", "https://staging-api.fluxpay.app/")}\"")
            buildConfigField("boolean", "ENABLE_LOGGING", "true")
            buildConfigField("boolean", "SECURE_SCREEN", "true")
            resValue("string", "app_name", "FluxPay Staging")
        }
        create("prod") {
            dimension = "environment"
            buildConfigField("String", "BASE_URL", "\"${propertyOr("fluxpay.prodUrl", "https://api.fluxpay.app/")}\"")
            buildConfigField("boolean", "ENABLE_LOGGING", "false")
            buildConfigField("boolean", "SECURE_SCREEN", "true")
            resValue("string", "app_name", "FluxPay")
        }
    }

    buildTypes {
        debug {
            isDebuggable = true
        }
        release {
            // R8: shrink, optimize and obfuscate for Google Play.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = if (hasReleaseKeystore) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" }
    }
}

// A dev build always talks to a local server over cleartext, so never ship a devRelease.
androidComponents {
    beforeVariants { variant ->
        if (variant.flavorName == "dev" && variant.buildType == "release") variant.enable = false
    }
}

dependencies {
    implementation(project(":core:common"))
    implementation(project(":core:domain"))
    implementation(project(":core:data"))
    implementation(project(":core:network"))
    implementation(project(":core:database"))
    implementation(project(":core:ui"))

    implementation(project(":feature:auth"))
    implementation(project(":feature:dashboard"))
    implementation(project(":feature:transfer"))
    implementation(project(":feature:transactions"))
    implementation(project(":feature:settings"))
    implementation(project(":feature:budget"))
    implementation(project(":feature:business"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.fragment.ktx) // MainActivity is a FragmentActivity for BiometricPrompt
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.hilt.navigation.compose)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    // Memory leak detection — debug builds only, never shipped.
    debugImplementation(libs.leakcanary)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.test.manifest)
}
