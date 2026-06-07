# Android Project Structure

ALAFIA/
└── Android/
    ├── app/
    │   ├── src/
    │   │   ├── main/
    │   │   │   ├── java/com/alafia/android/
    │   │   │   │   ├── api/
    │   │   │   │   │   ├── ApiClient.kt
    │   │   │   │   │   ├── ApiService.kt
    │   │   │   │   │   ├── AuthInterceptor.kt
    │   │   │   │   │   └── KeychainHelper.kt
    │   │   │   │   ├── models/
    │   │   │   │   │   └── Models.kt
    │   │   │   │   ├── schemas/
    │   │   │   │   │   └── Schemas.kt
    │   │   │   │   ├── ui/
    │   │   │   │   │   └── theme/
    │   │   │   │   │       └── Theme.kt
    │   │   │   │   ├── views/
    │   │   │   │   │   ├── auth/
    │   │   │   │   │   │   ├── LoginScreen.kt
    │   │   │   │   │   │   └── RegisterScreen.kt
    │   │   │   │   │   ├── components/
    │   │   │   │   │   │   └── SharedComponents.kt
    │   │   │   │   │   └── main/
    │   │   │   │   │       └── MainTabView.kt
    │   │   │   │   └── MainActivity.kt
    │   │   │   ├── res/
    │   │   │   │   ├── values/
    │   │   │   │   │   ├── colors.xml
    │   │   │   │   │   ├── strings.xml
    │   │   │   │   │   └── styles.xml
    │   │   │   │   └── layout/
    │   │   │   └── AndroidManifest.xml
    │   │   ├── test/
    │   │   └── androidTest/
    │   ├── build.gradle
    │   └── proguard-rules.pro
    ├── gradle/
    │   └── wrapper/
    │       └── gradle-wrapper.properties
    ├── build.gradle
    ├── settings.gradle
    ├── gradle.properties
    ├── README.md
    ├── .gitignore
    └── ARCHITECTURE.md
