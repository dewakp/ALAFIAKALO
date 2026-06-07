# ALAFIA Android App

A modern Android companion application for ALAFIA health and wellness platform, built with Kotlin and Jetpack Compose.

## Features

- **Authentication**: Secure login and registration
- **Fitness Tracking**: Log and monitor workouts and physical activity
- **Mood Tracking**: Track emotional states and identify patterns
- **Nutrition Logging**: Record meals and nutrition information
- **Lab Results**: Store and view medical test results
- **Medications**: Manage medications and prescriptions
- **Lifestyle Tracking**: Monitor daily lifestyle habits
- **AI Chat**: Get health insights from AI-powered assistant
- **Dashboard**: Overview of your health metrics

## Architecture

The app is built using modern Android development best practices:

- **Kotlin** for type-safe code
- **Jetpack Compose** for declarative UI
- **Retrofit** for REST API communication
- **EncryptedSharedPreferences** for secure local storage
- **Material Design 3** for consistent UI

## Project Structure

```
app/src/main/java/com/alafia/android/
├── api/
│   ├── ApiClient.kt
│   ├── ApiService.kt
│   ├── AuthInterceptor.kt
│   └── KeychainHelper.kt
├── models/
│   └── Models.kt
├── schemas/
│   └── Schemas.kt
├── ui/
│   └── theme/
│       └── Theme.kt
├── views/
│   ├── auth/
│   │   ├── LoginScreen.kt
│   │   └── RegisterScreen.kt
│   ├── components/
│   │   └── SharedComponents.kt
│   └── main/
│       └── MainTabView.kt
└── MainActivity.kt
```

## Getting Started

### Prerequisites

- Android Studio 2022.1 or later
- Android SDK 24+ (API level 24)
- JDK 17

### Setup

1. Clone the repository
2. Open the Android folder in Android Studio
3. Sync gradle files
4. Update the API base URL in `ApiClient.kt` if needed
5. Run the app on an emulator or device

## Configuration

### API Configuration

Edit `ApiClient.kt` to change the backend URL:

```kotlin
private const val BASE_URL = "http://your-backend-url/api/"
```

For development with a local backend:
```kotlin
private const val BASE_URL = "http://10.0.2.2:8000/api/" // For emulator
private const val BASE_URL = "http://localhost:8000/api/"  // For physical device
```

## Building

### Debug Build
```bash
./gradlew build
```

### Release Build
```bash
./gradlew build -PreleaseCode=true
```

### Run on Device
```bash
./gradlew installDebug
```

## Testing

To run tests:
```bash
./gradlew test
```

## Dependencies

- AndroidX Core, Lifecycle, Navigation
- Jetpack Compose 1.6.0+
- Retrofit 2.9.0
- Gson 2.10.1
- OkHttp 4.11.0
- Material3
- Security Crypto

## Authentication

The app uses JWT token-based authentication. Tokens are securely stored using Android's EncryptedSharedPreferences.

## API Integration

The app communicates with the ALAFIA backend API. All requests include the authorization token automatically via the `AuthInterceptor`.

## License

Proprietary - ALAFIA

## Support

For issues and questions, please contact the development team.
