# Pariksha Copilot Android - ProGuard Rules
-keep class com.google.ai.client.generativeai.** { *; }
-keep class kotlinx.serialization.** { *; }
-keepattributes *Annotation*
-dontwarn org.bouncycastle.**
-dontwarn org.conscrypt.**
-dontwarn org.openjsse.**
