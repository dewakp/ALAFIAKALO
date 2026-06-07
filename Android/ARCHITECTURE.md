# ALAFIA Android Architecture

## Overview

The ALAFIA Android app follows Clean Architecture principles combined with MVVM pattern for a scalable and maintainable codebase.

## Architecture Layers

### 1. **Presentation Layer** (`views/`)
- UI components built with Jetpack Compose
- Screens for different features
- Reusable components in `SharedComponents`

### 2. **API/Networking Layer** (`api/`)
- `ApiService`: Retrofit interface for API endpoints
- `ApiClient`: Singleton for Retrofit instance management
- `AuthInterceptor`: Handles token injection in requests
- `KeychainHelper`: Secure token storage

### 3. **Data Layer** (`models/`, `schemas/`)
- `Models.kt`: Core data models (User, FitnessLog, etc.)
- `Schemas.kt`: Request/Response schemas for API communication

### 4. **UI Theme Layer** (`ui/theme/`)
- `Theme.kt`: Material Design 3 theming
- Color schemes and typography definitions

## Key Components

### Authentication Flow
1. User enters credentials on LoginScreen or RegisterScreen
2. Request is sent to backend via ApiService
3. Token is received and stored securely in KeychainHelper
4. AuthInterceptor automatically adds token to all subsequent requests
5. Navigation occurs to main app

### API Communication
- All API calls are done via ApiService interface
- Retrofit handles serialization/deserialization with Gson
- OkHttp logging interceptor for debugging
- Automatic token injection via AuthInterceptor

### Secure Storage
- Uses EncryptedSharedPreferences for token storage
- Java 17 compatible encryption with AES256

## Project Structure

```
api/
├── ApiClient.kt          # Retrofit instance management
├── ApiService.kt         # API endpoints definition
├── AuthInterceptor.kt    # Token injection interceptor
└── KeychainHelper.kt     # Secure credential storage

models/
└── Models.kt             # Core data models

schemas/
└── Schemas.kt            # Request/Response DTOs

ui/
└── theme/
    └── Theme.kt          # Material Design 3 theme

views/
├── auth/
│   ├── LoginScreen.kt
│   └── RegisterScreen.kt
├── components/
│   └── SharedComponents.kt
└── main/
    └── MainTabView.kt    # Bottom nav + screens
```

## Navigation
- Uses Jetpack Navigation Compose
- Two-level navigation:
  1. Outer: Login → Register → Main
  2. Inner: Dashboard → Fitness → Mood → Nutrition → More

## State Management
- Uses Compose state (remember, mutableStateOf)
- Coroutines for async operations
- Simple state handling for MVP phase

## Dependency Management
- AndroidX libraries for compatibility
- Material3 for modern UI
- Retrofit for REST API
- Security Crypto for encryption
- Kotlin Coroutines for async

## Future Enhancements
- [ ] ViewModel and Repository pattern for better state management
- [ ] Room database for local caching
- [ ] WorkManager for background sync
- [ ] Hilt for dependency injection
- [ ] Unit tests and instrumented tests
- [ ] Analytics integration
- [ ] Offline-first capability
