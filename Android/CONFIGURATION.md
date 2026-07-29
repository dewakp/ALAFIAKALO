# Android App Configuration

## Environment Configuration

The Android app can be configured for different environments (development, staging, production).

## API Endpoint Configuration

### Current Configuration
**File**: `app/src/main/java/com/alafia/android/api/ApiClient.kt`

```kotlin
private const val BASE_URL = "http://localhost:8000/api/"
```

### For Different Environments

#### Local Development (Emulator)
```kotlin
private const val BASE_URL = "http://10.0.2.2:8000/api/"
```

#### Local Development (Physical Device)
First, find your computer's local IP:
```bash
ifconfig | grep "inet "  # macOS/Linux
ipconfig               # Windows
```

Then use that IP:
```kotlin
private const val BASE_URL = "http://192.168.1.100:8000/api/"
```

#### Staging Environment
```kotlin
private const val BASE_URL = "https://staging-api.alafia.app/api/"
```

#### Production Environment
```kotlin
private const val BASE_URL = "https://api.alafia.app/api/"
```

## Build Configuration

### Debug vs Release Builds

**Debug Build** (`build.gradle`):
- Debuggable
- Full logging enabled
- No minification
- Faster builds

**Release Build**:
- Not debuggable
- Minification enabled
- ProGuard rules applied
- Optimized for size

### Build Types

```gradle
buildTypes {
    debug {
        minifyEnabled false
        debuggable true
    }
    release {
        minifyEnabled false
        proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
    }
}
```

## Build Variants

Create custom build variants by adding flavors:

```gradle
flavorDimensions "environment"

productFlavors {
    development {
        dimension "environment"
        applicationIdSuffix ".dev"
        versionNameSuffix "-dev"
    }
    
    staging {
        dimension "environment"
        applicationIdSuffix ".staging"
        versionNameSuffix "-staging"
    }
    
    production {
        dimension "environment"
    }
}
```

Then build specific variant:
```bash
./gradlew assembleDevelopmentDebug
./gradlew assembleStagingRelease
./gradlew assembleProductionRelease
```

## Resource Configuration

### Build-time Constants

Add to `build.gradle`:
```gradle
buildTypes {
    debug {
        buildConfigField "String", "API_BASE_URL", "\"http://10.0.2.2:8000/api/\""
    }
    release {
        buildConfigField "String", "API_BASE_URL", "\"https://api.alafia.app/api/\""
    }
}
```

Access in code:
```kotlin
val baseUrl = BuildConfig.API_BASE_URL
```

## Manifest Configuration

### Debugging
The `AndroidManifest.xml` includes `android:debuggable="true"` for debug builds only.

### Permissions
Required permissions are declared in `AndroidManifest.xml`:
```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
```

## Network Security

### SSL Certificate Pinning — intentionally NOT used

We rely on standard system TLS validation (the Android trust store +
`network_security_config` below), and deliberately do **not** certificate-pin.

`api.alafia.app` is served by Cloud Run behind **Google-managed certificates
that auto-rotate**, so a hardcoded leaf pin would break the app on every
rotation. (This exact bug shipped once on iOS as a stale placeholder pin that
failed every request with `URLError.cancelled` — see `IOS/.../APIClient.swift`.)

Do NOT add the example below to `ApiClient.kt`. If pinning is ever truly
required, pin the **Google Trust Services intermediate** SPKI (stable for
years), never the auto-rotated leaf, and ship pin updates ahead of any CA
migration:

```kotlin
// ⚠️ Reference only — do not enable against api.alafia.app's managed cert.
val certificatePinner = CertificatePinner.Builder()
    .add("api.alafia.app", "sha256/<REAL_GTS_INTERMEDIATE_SPKI_HASH>")
    .build()
```

### Network Security Config

Create `res/xml/network_security_config.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="false">
        <domain includeSubdomains="true">api.alafia.app</domain>
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </domain-config>
</network-security-config>
```

Reference in `AndroidManifest.xml`:
```xml
<application
    android:networkSecurityConfig="@xml/network_security_config"
    ...>
</application>
```

## Keystore Configuration

### Debug Keystore
- Automatically created by Android Studio
- Location: `~/.android/debug.keystore`
- Password: `android`
- Alias: `androiddebugkey`

### Release Keystore
Create your own for release builds:
```bash
keytool -genkey -v -keystore ~/.alafia/release.keystore \
  -keyalg RSA -keysize 2048 -validity 10000 -alias alafia
```

Use in `build.gradle`:
```gradle
signingConfigs {
    release {
        storeFile file('/path/to/release.keystore')
        storePassword = System.getenv("KEYSTORE_PASSWORD")
        keyAlias = "alafia"
        keyPassword = System.getenv("KEY_PASSWORD")
    }
}

buildTypes {
    release {
        signingConfig signingConfigs.release
    }
}
```

## Gradle Properties

Edit `gradle.properties` for project-wide settings:
```properties
android.useAndroidX=true
android.enableJetifier=true
kotlin.code.style=official
```

## Version Configuration

Edit app version in `app/build.gradle`:
```gradle
defaultConfig {
    versionCode 1        # Internal version
    versionName "1.0.0"  # User-facing version
}
```

Version naming convention:
- Major.Minor.Patch (e.g., 1.0.0)
- Increment versionCode with each release

## Dependency Versions

Update library versions in `app/build.gradle` to get latest:
```bash
./gradlew dependencyUpdates
```

## Testing Configuration

Configure test runners:
```gradle
testInstrumentationRunner "androidx.test.runner.AndroidJUnitRunner"
```

Run tests:
```bash
./gradlew test                    # Unit tests
./gradlew connectedAndroidTest   # Instrumented tests
```

## Development Tips

1. **Always use relative import paths** in build.gradle
2. **Keep credentials out of Git** - use environment variables
3. **Use BuildConfig** for environment-specific values
4. **Test on multiple API levels** (24, 28, 33, 34)
5. **Verify ProGuard rules** don't break your app in release

## Troubleshooting

### API Connection Issues
- Verify BASE_URL in ApiClient.kt
- Check emulator can reach host (10.0.2.2)
- Enable HTTP in Network Security Config for dev

### Build Failures
```bash
./gradlew clean
./gradlew build
```

### Keystore Issues
```bash
keytool -list -v -keystore ~/.android/debug.keystore
```

## References

- [Android Build Configuration](https://developer.android.com/studio/build)
- [Build Variants](https://developer.android.com/studio/build/build-variants)
- [Network Security](https://developer.android.com/training/articles/security-config)
