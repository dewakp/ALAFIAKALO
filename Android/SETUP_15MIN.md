# 15-Minute Android Setup Guide

Get the ALAFIA Android app up and running in 15 minutes.

## ⏱️ Timeline

- **Minutes 1-2**: Prerequisites check
- **Minutes 3-5**: Open project in Android Studio
- **Minutes 6-8**: Configure API endpoint
- **Minutes 9-12**: Build and run
- **Minutes 13-15**: Verify functionality

---

## ✅ Minutes 1-2: Prerequisites Check

### Required Software
```bash
# Verify Android Studio is installed
# Android Studio 2022.1+

# Verify Java/Kotlin
java -version    # Should be 17+
```

### Required SDKs
Android Studio → SDK Manager:
- [ ] Android SDK 34 (API 34)
- [ ] Android SDK 24+ (minimum API)
- [ ] Build Tools 34.x
- [ ] Android Emulator (optional, or use device)

**Status**: If all checked, continue. Otherwise, install via Android Studio.

---

## ✅ Minutes 3-5: Open Project

### Step 1: Open Android Studio
1. Launch Android Studio
2. File → Open
3. Navigate to: `/path/to/ALAFIA/Android`
4. Click "Open"

### Step 2: Wait for Gradle Sync
- Android Studio automatically syncs gradle
- Watch bottom status bar for "Gradle sync finished"
- Takes 2-3 minutes (depends on internet speed)

**Status**: Gradle sync should complete without errors.

### Step 3: Verify No Errors
- Check if there are any red error markers
- If errors exist: Tools → Invalidate Caches → Restart
- Then wait for resync

**Status**: No error markers visible.

---

## ✅ Minutes 6-8: Configure API Endpoint

### Step 1: Open ApiClient
1. In Android Studio, open file:
   ```
   app/src/main/java/com/alafia/android/api/ApiClient.kt
   ```
2. Find line with `BASE_URL`:
   ```kotlin
   private const val BASE_URL = "http://localhost:8000/api/"
   ```

### Step 2: Set Correct URL

Choose based on your setup:

**Option A: Android Emulator (local backend)**
```kotlin
private const val BASE_URL = "http://10.0.2.2:8000/api/"
```

**Option B: Physical Device (local backend)**
```kotlin
# First, find your computer's IP:
ifconfig | grep "inet "    # macOS/Linux
ipconfig                   # Windows

# Then use it:
private const val BASE_URL = "http://192.168.1.100:8000/api/"
```

**Option C: Remote Server**
```kotlin
private const val BASE_URL = "https://your-server.com/api/"
```

### Step 3: Save
- Press Cmd+S (macOS) or Ctrl+S (Windows/Linux)

**Status**: URL configured and saved.

---

## ✅ Minutes 9-12: Build and Run

### Option A: Via Android Studio (Easiest)

**Step 1**: Select Target
- Top toolbar: Select device dropdown
- Choose emulator or connected physical device

**Step 2**: Click Run
- Click the green play button (Run)
- Building will start (takes 1-2 minutes first time)

**Step 3**: Wait for Launch
- App should appear on emulator/device
- Shows login screen

**Status**: App is running and showing login screen.

### Option B: Via Terminal

**Step 1**: Build
```bash
cd /path/to/ALAFIA/Android
./gradlew build
```

**Step 2**: Install
```bash
./gradlew installDebug
```

**Step 3**: Run
```bash
adb shell am start -n com.alafia.android/.MainActivity
```

**Status**: App launching on device.

---

## ✅ Minutes 13-15: Verify Functionality

### Check Login Screen
- [ ] App is visible on device
- [ ] See "ALAFIA" title
- [ ] See username field
- [ ] See password field
- [ ] See login button

### Try Navigation
- [ ] Click "Don't have an account? Register"
- [ ] See registration form appears
- [ ] Click back to return to login

### Check API Connectivity
**With Backend Running:**
- [ ] Enter valid credentials
- [ ] Click Login
- [ ] Should authenticate successfully
- [ ] Navigate to main tabs

**Without Backend Running:**
- [ ] Enter any credentials
- [ ] Click Login
- [ ] Should see error message in toast
- [ ] Check Logcat for network error

### View Logcat
- Android Studio → View → Tool Windows → Logcat
- Filter: package:com.alafia
- Should see successful API calls or connection errors

---

## 🎉 Success Checklist

You're done if all checked:
- [ ] Android Studio opened ALAFIA/Android
- [ ] Gradle synced without errors
- [ ] API endpoint configured
- [ ] App built successfully
- [ ] App runs on emulator/device
- [ ] Login screen visible
- [ ] Can navigate between screens
- [ ] API connectivity verified (errors or success)

---

## 🆘 Quick Troubleshooting

### Gradle Sync Fails
```bash
./gradlew clean
./gradlew build
```

### Cannot Connect to Backend
- Verify backend is running: `curl http://localhost:8000/api/`
- Check BASE_URL matches your backend
- For emulator: use `10.0.2.2`
- For device: use computer's actual IP

### Emulator Issues
```bash
# Kill and restart emulator
adb devices          # List devices
adb emu kill         # Kill emulator
# Then restart from Android Studio
```

### App Crashes on Launch
- Check Logcat for errors
- Look for "Exception" or "Error" lines
- Most common: Wrong API endpoint

### File Not Found Errors
- Verify file path is exactly:
  `app/src/main/java/com/alafia/android/api/ApiClient.kt`
- Use Android Studio file navigator if uncertain

---

## 📱 Next Steps (After Setup)

1. **Test Login Flow**: Use test credentials from backend
2. **Test API Calls**: Navigate to different tabs
3. **Review Code**: Read ARCHITECTURE.md
4. **Add Features**: See DEVELOPMENT.md for guides
5. **Run Tests**: `./gradlew test`

---

## 📚 Documentation

- **Quick Reference**: See QUICK_REFERENCE.md
- **Full Development Guide**: See DEVELOPMENT.md
- **Architecture Details**: See ARCHITECTURE.md
- **Configuration**: See CONFIGURATION.md

---

## ✨ You're Ready!

The Android app is now set up and running. Start by testing the login screen with your backend credentials.

**Questions?** Check the documentation files or your backend logs for API errors.

**Need Help?** Review QUICK_REFERENCE.md for common tasks and troubleshooting.

---

**Happy coding! 🚀**
