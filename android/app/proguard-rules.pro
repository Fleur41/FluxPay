# FluxPay R8 rules. Libraries (Retrofit, OkHttp, Room, Hilt, Moshi codegen, Compose)
# ship their own consumer rules; only app-specific keeps live here.

# Keep line numbers for readable crash reports, but hide original file names.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# DTOs are (de)serialized by generated Moshi adapters (see :core:network consumer-rules.pro).
-keep class com.fluxpay.core.network.dto.** { *; }

# Room entities are read via generated code, but keep field names stable for schema export tooling.
-keep class com.fluxpay.core.database.entity.** { *; }

# Strip verbose logging from release builds.
-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
}

# OkHttp optional TLS providers.
-dontwarn org.bouncycastle.**
-dontwarn org.conscrypt.**
-dontwarn org.openjsse.**
