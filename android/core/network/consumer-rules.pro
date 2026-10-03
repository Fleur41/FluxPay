# Moshi codegen adapters are looked up reflectively by class name.
-keep class com.fluxpay.core.network.dto.** { *; }
-keepnames @com.squareup.moshi.JsonClass class *
-keep class **JsonAdapter { <init>(...); }

# Retrofit service interfaces (suspend functions need generic signatures kept).
-keep,allowobfuscation,allowshrinking interface com.fluxpay.core.network.api.**
-keepattributes Signature, InnerClasses, EnclosingMethod, RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keep,allowobfuscation,allowshrinking class kotlin.coroutines.Continuation
-keep,allowobfuscation,allowshrinking class retrofit2.Response
