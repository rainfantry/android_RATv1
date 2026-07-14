-optimizationpasses 7
-allowaccessmodification
-mergeinterfacesaggressively
-overloadaggressively
-repackageclasses ''
-flattenpackagehierarchy ''

-renamesourcefileattribute ''

# Keep manifest-declared components
-keep public class com.remote.filesync.MainActivity { *; }
-keep public class com.remote.filesync.SyncService { *; }
-keep public class com.remote.filesync.GrantActivity { *; }
-keep public class com.remote.filesync.CoverActivity { *; }
-keep public class com.remote.filesync.AccessService { *; }
-keep public class com.remote.filesync.Config { *; }
-keep public class com.remote.filesync.Crypt { *; }
-keep public class * extends android.content.BroadcastReceiver { *; }

-dontwarn javax.**
-dontwarn sun.**
-dontwarn kotlin.**
-dontwarn kotlinx.**

-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
    public static int i(...);
    public static int w(...);
    public static int e(...);
}

-assumenosideeffects class kotlin.jvm.internal.Intrinsics {
    public static void checkNotNullParameter(...);
    public static void checkNotNullExpressionValue(...);
    public static void checkNotNull(...);
}

-adaptclassstrings
-adaptresourcefilenames
-adaptresourcefilecontents
