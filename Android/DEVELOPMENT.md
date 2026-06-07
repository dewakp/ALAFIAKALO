# Android Development Guide

## Getting Started

### Prerequisites
- Android Studio 2022.1+
- Android SDK (API 24-34)
- JDK 17
- Kotlin 1.9.10+

### Initial Setup

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd ALAFIA/Android
   ```

2. **Open in Android Studio**
   - File → Open → Select ALAFIA/Android folder
   - Android Studio will automatically download gradle and dependencies

3. **Configure Backend URL**
   - Edit `app/src/main/java/com/alafia/android/api/ApiClient.kt`
   - Update `BASE_URL` to match your backend:
     ```kotlin
     // For Android Emulator
     private const val BASE_URL = "http://10.0.2.2:8000/api/"
     
     // For Physical Device
     private const val BASE_URL = "http://192.168.x.x:8000/api/"
     ```

## Running the App

### Via Android Studio
1. Select emulator or device
2. Click "Run" (play icon)
3. App will build and launch

### Via Terminal
```bash
# Debug build and install
./gradlew installDebug

# Run on device (must be connected)
./gradlew build
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Run app after installation
adb shell am start -n com.alafia.android/.MainActivity
```

## Development Workflow

### Adding a New API Endpoint

1. **Add to ApiService** (`api/ApiService.kt`)
   ```kotlin
   @GET("endpoint")
   suspend fun getEndpoint(): ResponseType
   ```

2. **Create Request/Response Schemas** (`schemas/Schemas.kt`)
   ```kotlin
   data class EndpointRequest(...)
   data class EndpointResponse(...)
   ```

3. **Create/Update Models** (`models/Models.kt`)
   ```kotlin
   data class YourModel(...)
   ```

### Adding a New Screen

1. **Create Screen Composable** in appropriate `views/` subfolder
   ```kotlin
   @Composable
   fun YourScreen(
       activity: MainActivity,
       navController: NavHostController? = null
   ) {
       // Your UI here
   }
   ```

2. **Add Navigation Route** in `MainTabView.kt` or `MainActivity.kt`
   ```kotlin
   composable("your-route") {
       YourScreen(activity)
   }
   ```

3. **Add Navigation Button** in existing screens if needed

### Adding Dependencies

1. Edit `app/build.gradle`
2. Add to dependencies block
3. Sync gradle:
   ```bash
   ./gradlew build
   ```

## Debugging

### Logcat
- Android Studio → View → Tool Windows → Logcat
- Filter by package:
  ```
  tag:"ALAFIA" or package:com.alafia
  ```

### Network Debugging
- OkHttp logging is already enabled (see ApiClient)
- Check Logcat for API request/response details
- Level: `BODY` shows full request/response

### Breakpoints
1. Click line number to set breakpoint
2. Run app in debug mode
3. Interact to trigger breakpoint
4. Use debug panel to step through

## Testing

### Unit Tests
```bash
./gradlew test
```

### Instrumented Tests
```bash
./gradlew connectedAndroidTest
```

### Manual Testing Checklist
- [ ] Login with valid credentials
- [ ] Register new account
- [ ] Navigate between tabs
- [ ] Add fitness entry
- [ ] Add mood entry
- [ ] Add nutrition entry
- [ ] View lab results
- [ ] View medications
- [ ] Logout and verify login required

## Building for Release

### Generate Key Store
```bash
keytool -genkey -v -keystore ~/release.keystore -keyalg RSA -keysize 2048 -validity 10000 -alias alafia
```

### Sign APK
1. Build → Generate Signed Bundle / APK
2. Select key store and alias
3. Use release build type

## Troubleshooting

### Build Issues
```bash
# Clean and rebuild
./gradlew clean build

# Update gradle
./gradlew wrapper --gradle-version 8.1
```

### Connection Issues
- Verify backend is running
- Check firewall rules
- Use `adb logcat` to see errors
- Verify API endpoint URL is correct

### API Authentication Issues
- Clear app data: Settings → Apps → ALAFIA → Storage → Clear Data
- Re-login to refresh token
- Check backend auth token expiration

## Code Style

The project follows Android/Kotlin conventions:
- Classes: PascalCase (MainActivity)
- Functions/Variables: camelCase (loginUser)
- Constants: UPPER_SNAKE_CASE (BASE_URL)
- Composables: PascalCase (LoginScreen)

## Resources

- [Android Docs](https://developer.android.com)
- [Jetpack Compose](https://developer.android.com/jetpack/compose)
- [Retrofit](https://square.github.io/retrofit/)
- [Material Design 3](https://m3.material.io/)

## Common Tasks

### Access Emulator Files
```bash
adb shell
cd /sdcard
ls -la
```

### View App Preferences
```bash
adb shell
cd /data/data/com.alafia.android/shared_prefs
cat *.xml
```

### Restart Emulator
```bash
adb reboot
```

### Capture Screenshot
```bash
adb shell screencap -p /sdcard/screenshot.png
adb pull /sdcard/screenshot.png ./screenshot.png
```

## Performance Tips

1. Use proper modifiers in Compose (Modifier.fillMaxSize())
2. Avoid recomposition with remember {}
3. Use LazyColumn for large lists
4. Keep network calls in coroutines
5. Profile with Android Profiler for memory leaks

## More Information

See [README.md](README.md) for project overview and [ARCHITECTURE.md](ARCHITECTURE.md) for architecture details.
