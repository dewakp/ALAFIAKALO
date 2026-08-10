# Android App Quick Reference Guide

## 🎯 Essential Files & Locations

### API Configuration
```
app/src/main/java/com/alafia/android/api/ApiClient.kt
- Line ~14: Configure BASE_URL
```

### Main Entry Point
```
app/src/main/java/com/alafia/android/MainActivity.kt
- App initialization & navigation setup
```

### Authentication
```
api/AuthInterceptor.kt      - Automatic token injection
api/KeychainHelper.kt       - Secure token storage
views/auth/LoginScreen.kt   - User login UI
views/auth/RegisterScreen.kt - User registration UI
```

### Feature Screens
```
views/main/MainTabView.kt   - Main navigation structure
  - DashboardScreen
  - FitnessScreen
  - MoodScreen
  - NutritionScreen
  - MoreScreen (Labs, Medications, Lifestyle, AI)
```

### Data Models
```
models/Models.kt   - Data classes (User, FitnessLog, etc.)
schemas/Schemas.kt - API request/response DTOs
```

### Theme & Styling
```
ui/theme/Theme.kt  - Material Design 3 colors & typography
res/values/colors.xml
res/values/strings.xml
res/values/styles.xml
```

## 🔧 Common Tasks

### Change API Endpoint
1. Open `app/src/main/java/com/alafia/android/api/ApiClient.kt`
2. Edit: `private const val BASE_URL = "..."`
3. Save and rebuild

### Add New Screen
1. Create file in `views/category/ScreenName.kt`
2. Add `@Composable` function
3. Add route in `MainTabView.kt` or `MainActivity.kt`
4. Add navigation button

### Add New API Endpoint
1. Add method in `api/ApiService.kt`
2. Create request/response in `schemas/Schemas.kt`
3. Create model in `models/Models.kt` if needed
4. Use in screens via `ApiClient.getApiService()`

### Change App Colors
1. Edit `app/src/main/res/values/colors.xml`
2. Update primary, secondary, error colors
3. Theme references in `ui/theme/Theme.kt`

### Build & Run
```bash
# Debug build & install
./gradlew installDebug

# Run on emulator
./gradlew build

# See logs
adb logcat | grep ALAFIA
```

## 📋 Verification Checklist

After initial setup:

- [ ] Android Studio opens project without errors
- [ ] Gradle syncs successfully
- [ ] No missing SDK warnings
- [ ] API endpoint configured matching your backend
- [ ] App builds successfully: `./gradlew build`
- [ ] App installs on emulator/device: `./gradlew installDebug`
- [ ] Login screen displays
- [ ] Can enter credentials
- [ ] Errors logged to Logcat when backend unreachable
- [ ] Navigation works between tabs
- [ ] Compose preview works in Android Studio

## 🐛 Troubleshooting Quick Fixes

### Build fails
```bash
./gradlew clean build
```

### Cannot connect to backend
- Check BASE_URL in ApiClient.kt
- Verify backend is running
- Use `10.0.2.2:8000` for emulator
- Use local IP for physical device: `192.168.x.x:8000`

### Gradle sync issues
```bash
./gradlew --refresh-dependencies
```

### App crashes
- Check Logcat: Android Studio → View → Tool Windows → Logcat
- Search for "exception" or "error"

### Authentication fails
- Backend must have auth endpoints implemented
- Check request/response in Logcat
- Verify credentials are correct

## 🏃 Quick Start Commands

```bash
# Navigate to Android folder
cd /path/to/ALAFIA/Android

# Build debug APK
./gradlew build

# Install on connected device
./gradlew installDebug

# Run app (after installing)
adb shell am start -n com.alafia.android/.MainActivity

# Run unit tests
./gradlew test

# Clean build
./gradlew clean build

# View gradle tasks
./gradlew tasks
```

## 📱 Test Credentials

Use these for testing (adjust based on your backend):
```
Username: demo
Password: demo123
Email: demo@alafia.app
```

## 🎨 UI Framework Notes

### Jetpack Compose Best Practices
- Use `remember { mutableStateOf() }` for state
- Leverage `@Composable` functions for reuse
- Use `Modifier` for spacing and sizing
- Material3 components for consistency

### Common Compose Modifiers
```kotlin
Modifier.fillMaxSize()      // Fill parent
Modifier.fillMaxWidth()     // Full width
Modifier.padding(16.dp)     // Add spacing
Modifier.size(48.dp)        // Fixed size
Modifier.weight(1f)         // Flex grow
```

## 🔐 Security Notes

- Tokens stored in EncryptedSharedPreferences
- JWT Bearer token format in Authorization header
- HTTPS recommended for production
- ProGuard rules protect release builds

## 📱 Supported Android Versions

- **Minimum**: Android 7.0 (API 24)
- **Target**: Android 14 (API 34)
- **Tested on**: API 24, 28, 31, 33, 34

## 🔗 Key Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| Retrofit | 2.9.0 | REST API client |
| Compose UI | 1.6.0 | Modern UI framework |
| Material 3 | 1.1.1 | Design system |
| OkHttp | 4.11.0 | HTTP client |
| Security Crypto | 1.1.0-alpha06 | Encryption |
| Kotlin | 1.9.10 | Language |

## 🚀 Performance Tips

1. Use `LazyColumn` for long lists
2. Remember state to prevent recomposition
3. Keep network calls in coroutines
4. Profile with Android Profiler
5. Test on real devices

## 📞 Getting Help

1. Check Logcat for error messages
2. Review DEVELOPMENT.md for detailed guide
3. Check ARCHITECTURE.md for design decisions
4. Review API endpoint in backend

## 🎯 Project Files Summary

| File | Purpose |
|------|---------|
| MainActivity.kt | App entry point |
| ApiClient.kt | API configuration |
| ApiService.kt | API endpoints |
| Models.kt | Data classes |
| LoginScreen.kt | Login UI |
| MainTabView.kt | Main navigation |
| Theme.kt | UI styling |
| AndroidManifest.xml | App configuration |
| build.gradle | Build configuration |
| README.md | Project overview |
| DEVELOPMENT.md | Development guide |

## ✅ First-Time Setup

1. **Clone/Extract** ALAFIA project
2. **Open** Android folder in Android Studio
3. **Wait** for Gradle sync (may take 2-3 minutes)
4. **Edit** `ApiClient.kt` - set BASE_URL
5. **Run** `./gradlew build` - should succeed
6. **Select** emulator or device
7. **Click** Run (play icon) - app should launch
8. **Test** login screen appears

---

**Happy Coding!** 🚀

For more details, see the comprehensive documentation:
- README.md - Overview
- DEVELOPMENT.md - Development guide  
- ARCHITECTURE.md - Technical details
- CONFIGURATION.md - Environment setup
