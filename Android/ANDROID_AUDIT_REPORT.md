# ALAFIA Android – Comprehensive Kotlin File Audit

> **Date**: June 2025  
> **Scope**: All 24 `.kt` files under `Android/app/src/main/java/com/alafia/android/`  
> **Base URL**: `http://10.0.2.2:8000/api/v1/` (emulator → localhost)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Per-File Audit](#per-file-audit)
3. [Cross-Cutting Issues](#cross-cutting-issues)
4. [Severity Matrix](#severity-matrix)
5. [Recommended Fixes](#recommended-fixes)

---

## Executive Summary

| Metric | Count |
|---|---|
| Total Files | 24 |
| Fully Functional Screens | 12 |
| **Stub/Placeholder Screens** | **6** |
| **Unreachable Screens** | **2** |
| Critical Bugs | 3 |
| Major Bugs | 5 |
| Minor/Style Issues | 8 |

### Top 3 Critical Issues
1. **6 stub screens** (Dashboard, Fitness, Labs, Medications, Lifestyle, AI Chat) — users see hardcoded text and NO data
2. **2 unreachable screens** (Privacy Settings, Chronic Conditions) — fully coded but NO navigation route
3. **MessagingScreen `isOwn` bug** — messages show on wrong side of chat

---

## Per-File Audit

---

### 1. `api/ApiClient.kt` (53 lines)

**Purpose**: Singleton Retrofit builder with OkHttp client.

**API Endpoints**: None directly — provides the Retrofit instance.

**User Interactions**: None (infrastructure).

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🔴 Major | `setBaseUrl(url: String)` sets internal `baseUrl` field and nulls `retrofit`/`apiService`, but **never uses the `url` parameter** when rebuilding. The `getApiService()` always reads from `baseUrl` which WAS updated — however the method name and pattern suggest the intent was correct. The real bug is that it's called nowhere and is dead code. |

**API Path Check**: `BASE_URL = "http://10.0.2.2:8000/api/v1/"` — ✅ correct for Android emulator.

---

### 2. `api/ApiService.kt` (504 lines)

**Purpose**: Retrofit interface defining ALL API endpoints.

**API Endpoints Defined**:

| Method | Path | Backend Match |
|---|---|---|
| `POST` | `auth/login` | ✅ |
| `POST` | `auth/register` | ✅ |
| `GET` | `users/me` | ✅ |
| `PATCH` | `users/me` | ⚠️ Backend uses `PUT` |
| `GET` | `fitness` | ✅ |
| `POST` | `fitness` | ✅ |
| `DELETE` | `fitness/{id}` | ✅ |
| `GET` | `mood/` | ✅ |
| `POST` | `mood/` | ✅ |
| `DELETE` | `mood/{id}` | ✅ |
| `GET` | `nutrition/` | ✅ |
| `POST` | `nutrition/` | ✅ |
| `DELETE` | `nutrition/{id}` | ✅ |
| `GET` | `nutrition/food-search` | ✅ |
| `GET` | `nutrition/food/{fdcId}` | ✅ |
| `GET` | `nutrition/daily-summary` | ✅ |
| `GET` | `labs` | ✅ |
| `POST` | `labs` | ✅ |
| `DELETE` | `labs/{id}` | ✅ |
| `GET` | `medications` | ✅ |
| `POST` | `medications` | ✅ |
| `PUT` | `medications/{id}` | ✅ |
| `DELETE` | `medications/{id}` | ✅ |
| `GET` | `lifestyle` | ✅ |
| `POST` | `lifestyle` | ✅ |
| `DELETE` | `lifestyle/{id}` | ✅ |
| `POST` | `ai/chat` | ✅ |
| `GET` | `privacy/settings` | ⚠️ Unconfirmed |
| `PUT` | `privacy/settings` | ⚠️ Unconfirmed |
| `POST` | `privacy/export` | ⚠️ Unconfirmed |
| `DELETE` | `privacy/delete-account` | ⚠️ Unconfirmed |
| `GET` | `chronic` | ✅ |
| `POST` | `chronic` | ✅ |
| `PUT` | `chronic/{id}` | ✅ |
| `DELETE` | `chronic/{id}` | ✅ |
| `GET` | `therapy-sessions` | ✅ |
| `POST` | `therapy-sessions` | ✅ |
| `GET` | `mental-health/stats` | ✅ |
| `GET` | `mental-health/assessments` | ✅ |
| `POST` | `mental-health/assessments` | ✅ |
| `DELETE` | `mental-health/assessments/{id}` | ✅ |
| `GET` | `mental-health/breathing` | ✅ |
| `POST` | `mental-health/breathing/sessions` | ✅ |
| `GET` | `mental-health/gratitude` | ✅ |
| `POST` | `mental-health/gratitude` | ✅ |
| `DELETE` | `mental-health/gratitude/{id}` | ✅ |
| `GET` | `community/dashboard` | ✅ |
| `GET` | `community/alerts` | ✅ |
| `PATCH` | `community/alerts/{id}/bookmark` | ✅ |
| `GET` | `community/guidelines` | ✅ |
| `GET` | `community/reports` | ✅ |
| `POST` | `community/reports` | ✅ |
| `DELETE` | `community/reports/{id}` | ✅ |
| `GET` | `community/categories` | ✅ |
| `GET` | `community/sources` | ✅ |
| `GET` | `community/subscriptions` | ✅ |
| `PUT` | `community/subscriptions` | ✅ |
| `POST` | `community/seed` | ✅ |
| `GET` | `roles/catalog` | ✅ |
| `GET` | `roles/categories` | ✅ |
| `GET` | `roles/me` | ✅ |
| `POST` | `roles/me/{roleSlug}` | ✅ |
| `DELETE` | `roles/me/{roleSlug}` | ✅ |
| `PUT` | `roles/me/primary/{roleSlug}` | ✅ |
| `GET` | `roles/me/professional` | ✅ |
| `PUT` | `roles/me/professional` | ✅ |
| `GET` | `sync/connections` | ✅ |
| `POST` | `sync/connections` | ✅ |
| `GET` | `sync/status` | ✅ |
| `POST` | `sync/ingest` | ✅ |
| `GET` | `calendar/events` | ✅ |
| `POST` | `calendar/events` | ✅ |
| `PUT` | `calendar/events/{id}` | ✅ |
| `DELETE` | `calendar/events/{id}` | ✅ |
| `PATCH` | `calendar/events/{id}/complete` | ✅ |
| `GET` | `calendar/categories` | ✅ |
| `GET` | `telehealth/sessions` | ✅ |
| `POST` | `telehealth/sessions` | ✅ |
| `PATCH` | `telehealth/sessions/{id}` | ✅ |
| `POST` | `telehealth/sessions/{id}/start` | ✅ |
| `POST` | `telehealth/sessions/{id}/end` | ✅ |
| `POST` | `telehealth/sessions/{id}/join` | ✅ |
| `POST` | `telehealth/sessions/{id}/leave` | ✅ |
| `GET` | `telehealth/sessions/{id}/rtc-config` | ✅ (defined but never called) |
| `GET` | `telehealth/sessions/{id}/notes` | ✅ |
| `POST` | `telehealth/sessions/{id}/notes` | ✅ |
| `DELETE` | `telehealth/notes/{id}` | ✅ |
| `GET` | `telehealth/sessions/{id}/transcripts` | ✅ |
| `GET` | `messaging/conversations` | ✅ |
| `POST` | `messaging/conversations` | ✅ |
| `GET` | `messaging/conversations/{id}/messages` | ✅ |
| `POST` | `messaging/conversations/{id}/messages` | ✅ |
| `POST` | `messaging/conversations/{id}/read` | ✅ |
| `GET` | `messaging/feed` | ✅ |
| `POST` | `messaging/feed` | ✅ |
| `GET` | `messaging/feed/{id}` | ✅ |
| `GET` | `messaging/feed/{id}/replies` | ✅ |
| `POST` | `messaging/feed/{id}/replies` | ✅ |
| `POST` | `messaging/feed/{id}/like` | ✅ |
| `DELETE` | `messaging/feed/{id}/like` | ✅ |
| `POST` | `messaging/follow/{userId}` | ✅ |
| `DELETE` | `messaging/follow/{userId}` | ✅ |

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🟡 Medium | `updateUser()` uses `@PATCH("users/me")` — backend likely expects `PUT`. Partial updates may fail or be rejected. |
| 2 | 🟡 Medium | `getTelehealthRTCConfig()` is defined but never called anywhere in the codebase. Dead code. |
| 3 | 🟢 Minor | Missing `GET ai/history` endpoint if the backend supports it. |

---

### 3. `api/AuthInterceptor.kt` (23 lines)

**Purpose**: OkHttp interceptor that adds `Authorization: Bearer <token>` header.

**API Endpoints**: N/A (infrastructure).

**User Interactions**: None.

**Bugs Found**: ✅ None. Clean implementation.

---

### 4. `api/KeychainHelper.kt` (57 lines)

**Purpose**: `EncryptedSharedPreferences` wrapper for `authToken`, `userId`, `userName`.

**API Endpoints**: N/A (storage).

**User Interactions**: None (called by other components).

**Bugs Found**: ✅ None. Clean implementation. Provides `isLoggedIn()`, `clearAll()`.

---

### 5. `models/Models.kt` (817 lines)

**Purpose**: All Gson-mapped data classes.

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🟡 Medium | `FitnessLog` uses raw snake_case field names (`user_id`, `log_date`, `activity_type`, etc.) **without** `@SerializedName`. Works with Gson's default field-name matching but is inconsistent with every other model in the file. |
| 2 | 🟡 Medium | `LabResult` — same issue: raw snake_case, no `@SerializedName`. |
| 3 | 🟡 Medium | `Medication` — same issue. |
| 4 | 🟡 Medium | `LifestyleEntry` — same issue. |
| 5 | 🟢 Minor | All other models (`MoodEntry`, `NutritionLog`, `TelehealthSession`, `Conversation`, etc.) correctly use `@SerializedName`. The inconsistency makes maintenance error-prone — a Gson policy change or ProGuard minification would break the unannotated models while the annotated ones survive. |

---

### 6. `schemas/Schemas.kt` (446 lines)

**Purpose**: Request/response schemas for all features.

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🟡 Medium | `LoginResponse` uses raw `access_token` / `token_type` without `@SerializedName`. Same Gson/ProGuard risk. |
| 2 | 🟡 Medium | `RegisterRequest` uses raw `full_name`, `date_of_birth` without annotation. |
| 3 | 🟡 Medium | `UserSchema` (45 fields) — ALL raw snake_case, no `@SerializedName` on any field. |
| 4 | 🟡 Medium | `UserUpdateRequest` — same as above. |
| 5 | 🟡 Medium | `FitnessLogRequest`, `FitnessLogResponse` — raw snake_case. |
| 6 | 🟡 Medium | `MedicationRequest`, `LabResultRequest`, `LifestyleEntryRequest` — raw snake_case. |
| 7 | 🟢 Minor | Nutrition, Mental Health, Community, Roles, Sync, Calendar, Telehealth, Messaging schemas all properly use `@SerializedName`. Inconsistency. |

---

### 7. `MainActivity.kt` (70 lines)

**Purpose**: Entry point. Sets up outer `NavHost` with `login`, `register`, `main` routes.

**API Endpoints Called**: None directly.

**User Interactions**:
| Action | Result |
|---|---|
| App launch | Checks `KeychainHelper.isLoggedIn()` → navigates to `login` or `main` |

**Bugs Found**: ✅ None.

---

### 8. `ui/theme/Theme.kt` (62 lines)

**Purpose**: Material3 light/dark color scheme.

**Bugs Found**: ✅ None.

---

### 9. `views/auth/LoginScreen.kt` (109 lines)

**Purpose**: Login form.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `POST auth/login` | "Log In" button |
| `GET users/me` | Automatically after successful login |

**User Interactions**:
| Element | Action |
|---|---|
| Username field | Text input |
| Password field | Text input (password-masked) |
| "Log In" button | Validates non-empty, calls login API, saves token/userId/userName, navigates to `main` |
| "Create Account" text | Navigates to `register` |

**Bugs Found**: ✅ None. Proper loading state, error handling with Toast.

---

### 10. `views/auth/RegisterScreen.kt` (148 lines)

**Purpose**: Registration form.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `POST auth/register` | "Create Account" button |
| `POST auth/login` | Automatically after register |
| `GET users/me` | Automatically after login |

**User Interactions**:
| Element | Action |
|---|---|
| Full Name, Email, Date of Birth, Password, Confirm Password fields | Text input |
| "Create Account" button | Validates passwords match, registers, auto-logins, navigates to `main` |
| "Already have an account?" text | Pops back to login |

**Bugs Found**: ✅ None.

---

### 11. `views/main/MainTabView.kt` (~355 lines)

**Purpose**: Bottom navigation shell + inner `NavHost` + MoreScreen + 6 inline stub screens.

**API Endpoints Called**: None (navigation wrapper).

**User Interactions**:
| Element | Action |
|---|---|
| Bottom nav: Dashboard | Navigates to `dashboard` (stub) |
| Bottom nav: Fitness | Navigates to `fitness` (stub) |
| Bottom nav: Mood | Navigates to `mood` (MoodScreen ✅) |
| Bottom nav: Nutrition | Navigates to `nutrition` (NutritionScreen ✅) |
| Bottom nav: More | Navigates to `more` (MoreScreen ✅) |
| MoreScreen buttons | Navigate to labs, medications, lifestyle, ai-chat, mental-health, community-health, roles, health-sync, calendar, telehealth, messaging, profile |
| Logout button | Clears KeychainHelper, navigates to `login` |

**Inner NavHost Routes Registered**: `dashboard`, `fitness`, `mood`, `nutrition`, `more`, `labs`, `medications`, `lifestyle`, `ai-chat`, `mental-health`, `community-health`, `roles`, `health-sync`, `calendar`, `telehealth`, `messaging`, `profile`

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🔴 **Critical** | **DashboardScreen** is a stub — shows only `DashboardCard("Welcome to ALAFIA", "Your health dashboard")`. No API calls, no data, no interactions. |
| 2 | 🔴 **Critical** | **FitnessScreen** is a stub — shows only `DashboardCard("Fitness Tracking", "Log workouts, steps, and activities")`. No API calls. |
| 3 | 🔴 **Critical** | **LabsScreen** is a stub — shows only `DashboardCard("Lab Results", "Track your lab work and test results")`. No API calls. |
| 4 | 🔴 **Critical** | **MedicationsScreen** is a stub — shows only `DashboardCard("Medications", "Manage your medications and reminders")`. No API calls. |
| 5 | 🔴 **Critical** | **LifestyleScreen** is a stub — shows only `DashboardCard("Lifestyle", "Track sleep, stress, and daily habits")`. No API calls. |
| 6 | 🔴 **Critical** | **AIChatScreen** is a stub — shows only `DashboardCard("AI Health Coach", "Chat with your personal health assistant")`. No API calls. |
| 7 | 🔴 **Critical** | **No `"privacy"` route** — `PrivacySettingsScreen.kt` exists and is fully implemented but has zero navigation entries. Screen is **unreachable**. |
| 8 | 🔴 **Critical** | **No `"chronic"` route** — `ChronicConditionsScreen.kt` exists and is fully implemented but has zero navigation entries. Screen is **unreachable**. |

---

### 12. `views/components/SharedComponents.kt` (96 lines)

**Purpose**: Reusable composables: `DashboardCard`, `StatsCard`, `LoadingIndicator`.

**Bugs Found**: ✅ None. Simple utility file.

---

### 13. `views/mood/MoodScreen.kt` (~303 lines)

**Purpose**: Mood tracking — list, add, delete.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET mood/` | Screen load (LaunchedEffect) |
| `POST mood/` | "Save" button in add dialog |
| `DELETE mood/{id}` | Delete button on mood card |

**User Interactions**:
| Element | Action |
|---|---|
| FAB (+) | Opens add mood dialog |
| Mood sliders | Adjust mood_score, energy_level, stress_level, anxiety_level, sleep_hours (1–10 / 0–12) |
| Text fields | emotions, triggers, coping_strategies, gratitude, journal |
| "Save" button | Creates mood entry, refreshes list |
| Delete icon on card | Deletes entry with confirmation implicit (immediate) |

**Bugs Found**: ✅ None. Fully functional with proper error handling.

---

### 14. `views/nutrition/NutritionScreen.kt` (~370 lines)

**Purpose**: Nutrition logging with USDA food search and daily summaries.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET nutrition/` | Tab 1 load |
| `POST nutrition/` | "Log" button |
| `DELETE nutrition/{id}` | Delete button on food card |
| `GET nutrition/food-search` | Typing in search field (debounced) |
| `GET nutrition/food/{fdcId}` | Selecting a USDA food result |
| `GET nutrition/daily-summary` | Tab 2 load / date change |

**User Interactions**:
| Element | Action |
|---|---|
| Tab 1 (Food Log) / Tab 2 (Daily Summary) | Switch views |
| USDA food search field | Triggers debounced food search |
| Food result click | Loads food detail, auto-populates nutrient fields |
| Food detail dialog | Shows full USDA nutrient data |
| Manual entry fields | meal_type, food_name, calories, protein, carbs, fat, fiber |
| "Log" button | Creates nutrition entry |
| Delete icon on food card | Deletes entry |
| Date picker on Daily Summary | Loads summary for selected date |

**Bugs Found**: ✅ None. Comprehensive and well-implemented.

---

### 15. `views/mentalhealth/MentalHealthScreen.kt` (~580 lines)

**Purpose**: Mental health dashboard with breathing exercises, gratitude journal, and clinical assessments.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET mental-health/stats` | Dashboard tab load |
| `GET mental-health/breathing` | Breathing tab load |
| `POST mental-health/breathing/sessions` | "Complete" button after breathing session |
| `GET mental-health/gratitude` | Gratitude tab load |
| `POST mental-health/gratitude` | "Save" button on gratitude form |
| `DELETE mental-health/gratitude/{id}` | Delete button |
| `GET mental-health/assessments` | Assessments tab load |
| `POST mental-health/assessments` | "Submit" button on assessment form |
| `DELETE mental-health/assessments/{id}` | Delete button |

**User Interactions**:
| Element | Action |
|---|---|
| 4 tabs | Dashboard, Breathing, Gratitude, Assessments |
| Breathing exercise cards | Start breathing session with animated timer (inhale/hold/exhale/hold2 phases) |
| Gratitude form | Add gratitude entry with text + category |
| Assessment form | PHQ-9, GAD-7, or WHO-5 clinical questionnaires with radio buttons |
| Dashboard wellness score | Shows aggregated mental health stats |

**Bugs Found**: ✅ None. Fully functional with animated breathing timer.

---

### 16. `views/community/CommunityHealthScreen.kt` (1515 lines)

**Purpose**: Public health alerts, guidelines, reports, and subscription management.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET community/dashboard` | Dashboard tab load |
| `GET community/alerts` | Alerts tab load |
| `GET community/guidelines` | Guidelines tab load |
| `GET community/reports` | Reports tab load |
| `GET community/categories` | Settings tab load |
| `GET community/sources` | Settings tab load |
| `GET community/subscriptions` | Settings tab load |
| `PUT community/subscriptions` | "Save" button on settings |
| `POST community/seed` | Auto-called when alerts list is empty |
| `PATCH community/alerts/{id}/bookmark` | Bookmark button on alert card |
| `POST community/reports` | "Submit Report" button |
| `DELETE community/reports/{id}` | Delete button on report card |

**User Interactions**:
| Element | Action |
|---|---|
| 5 tabs | Dashboard, Alerts, Guidelines, Reports, Settings |
| Alert cards | Tap opens detail bottom sheet with outbreak/recall info, recommended actions |
| Guideline cards | Tap opens detail sheet with full guideline text and recommendations |
| Bookmark toggle | Bookmarks/unbookmarks alerts |
| Report form | Submit reports with type, severity, location, description, symptoms |
| Subscription settings | Toggle categories, sources, severity levels, countries, notification channels |
| "Seed Data" | Auto-populates sample health alerts |

**Bugs Found**: ✅ None. Comprehensive and well-implemented.

---

### 17. `views/roles/RolesScreen.kt` (726 lines)

**Purpose**: User role management — persona summary, role assignment, professional profile.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET roles/me` | Screen load |
| `GET roles/catalog` | Add Role tab load |
| `POST roles/me/{roleSlug}` | "Add" button on role card |
| `DELETE roles/me/{roleSlug}` | "Remove" button on role card |
| `PUT roles/me/primary/{roleSlug}` | "Set Primary" button |
| `GET roles/me/professional` | Professional profile sheet load |
| `PUT roles/me/professional` | "Save" button on professional form |

**User Interactions**:
| Element | Action |
|---|---|
| 2 tabs | My Roles, Add Role |
| Role cards | Add, remove, set as primary |
| Professional profile FAB | Opens editor bottom sheet |
| Professional form fields | license, credentials, specialty, institution, education, practice years, hospital, telemedicine, languages, bio |
| Search + category filter | Filter available roles in catalog |

**Bugs Found**: ✅ None. Fully functional.

---

### 18. `views/sync/HealthSyncScreen.kt` (~400 lines)

**Purpose**: Health Connect integration — reads device health data and syncs to backend.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET sync/connections` | Screen load |
| `GET sync/status` | Screen load |
| `POST sync/connections` | Happens during first sync if no Health Connect connection exists |
| `POST sync/ingest` | "Sync Now" button |

**User Interactions**:
| Element | Action |
|---|---|
| Data type toggles | Enable/disable sync for: steps, heart_rate, workout, sleep, weight, blood_pressure, blood_oxygen, body_temperature, nutrition |
| "Sync Now" button | Requests Health Connect permissions, reads data, batch-uploads (200 per batch) |
| Connection status card | Shows provider, last sync time |
| Results display | Shows success/failed/skipped record counts |

**Health Connect Data Types Read**:
- `StepsRecord` → steps count
- `HeartRateRecord` → BPM samples
- `ExerciseSessionRecord` → workout type/duration/calories
- `SleepSessionRecord` → sleep duration
- `WeightRecord` → weight in kg
- `BloodPressureRecord` → systolic/diastolic
- `OxygenSaturationRecord` → SpO2 percentage
- `BodyTemperatureRecord` → temperature in Celsius
- `NutritionRecord` → calories/protein/carbs/fat

**Bugs Found**: ✅ None. Comprehensive implementation with deduplication via external IDs.

---

### 19. `views/calendar/CalendarScreen.kt` (~550 lines)

**Purpose**: Health calendar with event management.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET calendar/events` | Screen load + month navigation |
| `POST calendar/events` | "Save" button on event form |
| `PUT calendar/events/{id}` | "Save" button on edit form |
| `DELETE calendar/events/{id}` | Delete button on event card |
| `PATCH calendar/events/{id}/complete` | Complete button on event card |

**User Interactions**:
| Element | Action |
|---|---|
| Month navigation (← →) | Load events for prev/next month |
| Calendar grid | Tap date to select, shows events for that date |
| Event dots | Color-coded category indicators on calendar cells |
| Category filter chips | Filter events by category |
| Event cards | Show title, time, category, priority; complete/edit/delete actions |
| FAB (+) | Opens event creation form |
| Event form dialog | Title, description, category, date/time, recurrence, priority, location, all-day toggle |

**Bugs Found**: ✅ None. Fully functional calendar implementation.

---

### 20. `views/telehealth/TelehealthScreen.kt` (~730 lines)

**Purpose**: Telehealth session management with simulated video calls.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET telehealth/sessions` | Screen load |
| `POST telehealth/sessions` | "Create" button on session form |
| `PATCH telehealth/sessions/{id}` | Cancel button (sets status to "cancelled") |
| `POST telehealth/sessions/{id}/start` | "Start Session" button |
| `POST telehealth/sessions/{id}/end` | "End Call" button in video overlay |
| `POST telehealth/sessions/{id}/join` | "Join Session" button |
| `POST telehealth/sessions/{id}/leave` | Leave button in video overlay |
| `GET telehealth/sessions/{id}/notes` | Notes tab in detail sheet |
| `POST telehealth/sessions/{id}/notes` | "Add" button on note form |
| `DELETE telehealth/notes/{id}` | Delete button on note card |
| `GET telehealth/sessions/{id}/transcripts` | Transcripts tab in detail sheet |

**User Interactions**:
| Element | Action |
|---|---|
| Session filter tabs | My Sessions, Available, Completed |
| Session cards | Tap opens detail bottom sheet |
| Detail bottom sheet | 3 tabs: Info, Notes, Transcripts |
| Start/Join/Cancel buttons | Session lifecycle management |
| Video call overlay | Simulated call UI with camera/mic/chat toggles, timer, waiting room |
| Create session form | Type, specialty, scheduled time, complaint, priority, features |

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🟢 Minor | `getTelehealthRTCConfig()` endpoint is defined in `ApiService.kt` but **never called**. Video call is entirely simulated UI — no actual WebRTC. This is fine for MVP but should be documented. |

---

### 21. `views/messaging/MessagingScreen.kt` (1310 lines)

**Purpose**: Full messaging hub with DMs, clinical conversations, groups, and community feed.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET messaging/conversations` | Conversations view load |
| `POST messaging/conversations` | "Create" button on conversation form |
| `GET messaging/conversations/{id}/messages` | Chat view load |
| `POST messaging/conversations/{id}/messages` | Send button in chat |
| `POST messaging/conversations/{id}/read` | Chat view load (marks read) |
| `GET messaging/feed` | Feed view load |
| `POST messaging/feed` | "Publish" button on post form |
| `GET messaging/feed/{id}` | Post card tap (loads detail) |
| `GET messaging/feed/{id}/replies` | Post detail load |
| `POST messaging/feed/{id}/replies` | Reply send button |
| `POST messaging/feed/{id}/like` | Heart/like button |
| `DELETE messaging/feed/{id}/like` | Unlike button |

**User Interactions**:
| Element | Action |
|---|---|
| Hub categories | DMs, Clinical, Groups, Community Feed |
| Conversation list | Filtered by type; tap opens chat view |
| Chat view | Message bubbles, text input, send button |
| Back button in chat/feed | Returns to conversation list / hub |
| FAB in conversations | Opens create conversation sheet |
| FAB in feed | Opens create post sheet |
| Create conversation sheet | Type, title, member IDs, description, specialty, priority, urgent toggle |
| Create post sheet | Content (5000 char limit), visibility, topic, health category, hashtags, anonymous toggle |
| Post cards | Like, reply count, view count; tap opens detail |
| Post detail | Full post with replies, reply input |

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🔴 **Critical** | **`isOwn` message detection is wrong.** In `ChatView`, the code uses `val isOwn = msg.senderId == conversation.createdBy` — this checks if the message sender is the *conversation creator*, NOT the current user. All messages from non-creators will appear as "their own" and vice versa. **Fix**: use `msg.senderId == KeychainHelper.getUserId(context)?.toIntOrNull()`. |
| 2 | 🟢 Minor | `formatShortDate()` and `formatTime()` strip timezone info with `replace("+00:00", "Z")` — will break for non-UTC offsets (e.g., `+05:30`). Should use a full ISO parser. |

---

### 22. `views/profile/ProfileScreen.kt` (~295 lines)

**Purpose**: Comprehensive user profile editor with 35+ fields.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET users/me` | Screen load (LaunchedEffect) |
| `PATCH users/me` | "Save Profile" button |

**User Interactions**:
| Element | Action |
|---|---|
| Email field | Read-only display |
| Identity section | Full name, DOB (lockable), gender, sex at birth (lockable), blood type (lockable) |
| Insurance section | ID, provider, country |
| Physical section | Height, weight, target weight |
| Location section | Country, timezone, language, units |
| Health section | Allergies, intolerances, restrictions, preferences, family history |
| Fitness section | Activity level, exercise/week, goals, preferred activities |
| Lifestyle section | Occupation, smoking, alcohol, sleep schedule, stress |
| AI preferences | Coaching toggle, personality, complexity dropdowns |
| Privacy section | Data sharing consent, AI training consent toggles |
| "Save Profile" button | Sends all editable fields via `updateUser()` |

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🟡 Medium | Uses `PATCH users/me` (via `updateUser()` in ApiService) — backend may expect `PUT`. Same issue as ApiService #1. |
| 2 | 🟡 Medium | `UserSchema` and `UserUpdateRequest` have **no `@SerializedName` annotations** on any field (45+ fields each). Will break under ProGuard/R8 minification in release builds. |
| 3 | 🟢 Minor | No Toast or Snackbar for error display — uses inline `Text(message)` which could be missed if scrolled away. |

---

### 23. `views/privacy/PrivacySettingsScreen.kt` (~370 lines)

**Purpose**: GDPR/HIPAA privacy controls, data export, account deletion.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET privacy/settings` | Screen load |
| `PUT privacy/settings` | Any toggle change (immediate save per field) |
| `POST privacy/export` | "JSON" or "CSV" button in export dialog |
| `DELETE privacy/delete-account` | "Delete" button in confirmation dialog |

**User Interactions**:
| Element | Action |
|---|---|
| Data Sharing toggles | Anonymized analytics, collective insights, research participation |
| Communications toggles | Marketing emails, product updates, health reminders |
| AI Preferences | AI coaching toggle, AI memory toggle, explainability level dropdown |
| Security | Biometric auth toggle, session timeout dropdown |
| Compliance info card | Shows GDPR/HIPAA applicability |
| "Export My Data" button | Opens format selection dialog (JSON/CSV) |
| "Delete Account" button | Opens confirmation dialog → deletes account → navigates to login |

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🔴 **Critical** | **Screen is UNREACHABLE** — no navigation route exists in `MainTabView.kt`. The MoreScreen has no button for privacy settings. Fully implemented but users cannot access it. |
| 2 | ⚠️ Unconfirmed | Privacy API endpoints (`privacy/settings`, `privacy/export`, `privacy/delete-account`) are not in the verified backend routes list. These may 404 if the backend doesn't implement them. |

---

### 24. `views/chronic/ChronicConditionsScreen.kt` (~475 lines)

**Purpose**: Chronic condition management — list, add, edit, delete.

**API Endpoints Called**:
| Endpoint | Trigger |
|---|---|
| `GET chronic?is_active=true` | Screen load |
| `POST chronic` | "Create" button on condition form |
| `PUT chronic/{id}` | "Update" button on edit form |
| `DELETE chronic/{id}` | "Delete" button on condition card |

**User Interactions**:
| Element | Action |
|---|---|
| Condition cards | Display name, severity chip (color-coded), category, ICD-10, diagnosis date, physician, treatment plan |
| Edit button | Opens form pre-filled with condition data |
| Delete button | Deletes condition, refreshes list |
| FAB (+) | Opens add condition form |
| Condition form dialog | Name, category dropdown (10 options), severity dropdown (5 options), ICD-10 code, diagnosis date, physician, treatment plan, notes |
| Back arrow | `navController.popBackStack()` |

**Bugs Found**:
| # | Severity | Description |
|---|---|---|
| 1 | 🔴 **Critical** | **Screen is UNREACHABLE** — no navigation route exists in `MainTabView.kt`. Fully implemented with CRUD operations but users cannot access it. |
| 2 | 🟢 Minor | Form sends `Map<String, Any?>` instead of a typed request class. Works but loses compile-time safety. |
| 3 | 🟢 Minor | Uses deprecated `.capitalize()` (should use `.replaceFirstChar { it.uppercase() }`). |

---

## Cross-Cutting Issues

### Issue A: Inconsistent `@SerializedName` Usage

**Affected Files**: `Models.kt`, `Schemas.kt`

**Models WITH `@SerializedName`** (safe):
`MoodEntry`, `NutritionLog`, `USDAFoodResult`, `USDAFoodNutrient`, `USDAFoodDetail`, `DailySummary`, `PrivacySettings`, `ChronicCondition`, `TherapySession`, `MentalHealthAssessment`, `BreathingExerciseInfo`, `BreathingSessionResponse`, `GratitudeEntryResponse`, `MentalHealthStats`, all Community models, all Role models, `SyncConnection`, `SyncBatchResponse`, `SyncRecordResult`, `SyncStatusResponse`, `CalendarEvent`, `CalendarCategoryInfo`, `TelehealthSession`, `TelehealthParticipant`, `TelehealthNote`, `TelehealthTranscript`, `TelehealthRTCConfig`, `ICEServer`, `Conversation`, `ConversationMember`, `ConversationMessage`, `CommunityPost`, `PostReply`, `UserFollow`, `LikeResponse`

**Models WITHOUT `@SerializedName`** (at risk):
`FitnessLog`, `LabResult`, `Medication`, `LifestyleEntry`, `LoginResponse`, `RegisterRequest`, `UserSchema`, `UserUpdateRequest`, `FitnessLogRequest`, `FitnessLogResponse`, `MedicationRequest`, `LabResultRequest`, `LifestyleEntryRequest`

**Impact**: Works in debug builds. **Will break in release builds** when R8/ProGuard renames fields unless specific keep rules are in place.

### Issue B: PATCH vs PUT for User Updates

`ApiService.updateUser()` uses `@PATCH("users/me")`. If the backend `PUT /api/v1/users/me` endpoint doesn't accept PATCH, any profile updates silently fail or return 405.

### Issue C: No Offline / Error Retry

No caching strategy, no retry logic, no offline queue. Every API call is fire-and-forget. Network failures show a Toast and stop.

### Issue D: No Input Validation

Most forms allow submission with potentially invalid data (e.g., non-date strings in date fields, negative numbers in numeric fields). Backend validation catches errors but the UX is poor.

---

## Severity Matrix

### 🔴 Critical (must fix before release)

| # | File | Issue |
|---|---|---|
| C1 | `MainTabView.kt` | **DashboardScreen** is a stub — the FIRST screen users see is empty |
| C2 | `MainTabView.kt` | **FitnessScreen** is a stub — bottom nav tab shows nothing |
| C3 | `MainTabView.kt` | **LabsScreen** is a stub |
| C4 | `MainTabView.kt` | **MedicationsScreen** is a stub |
| C5 | `MainTabView.kt` | **LifestyleScreen** is a stub |
| C6 | `MainTabView.kt` | **AIChatScreen** is a stub |
| C7 | `MainTabView.kt` | **PrivacySettingsScreen** is unreachable — no route |
| C8 | `MainTabView.kt` | **ChronicConditionsScreen** is unreachable — no route |
| C9 | `MessagingScreen.kt` | **`isOwn` bug** — messages display on wrong side in chat |

### 🟡 Major (should fix)

| # | File | Issue |
|---|---|---|
| M1 | `ApiService.kt` | `PATCH users/me` may not match backend `PUT` |
| M2 | `Models.kt` | 4 models missing `@SerializedName` — breaks with ProGuard |
| M3 | `Schemas.kt` | 8 schema classes missing `@SerializedName` — breaks with ProGuard |
| M4 | `ApiClient.kt` | `setBaseUrl()` is dead code |
| M5 | `PrivacySettingsScreen.kt` | Privacy endpoints may not exist on backend |

### 🟢 Minor (nice to fix)

| # | File | Issue |
|---|---|---|
| m1 | `ApiService.kt` | `getTelehealthRTCConfig()` defined but unused |
| m2 | `ApiService.kt` | Missing `GET ai/history` endpoint |
| m3 | `MessagingScreen.kt` | Date parser strips only `+00:00`, breaks for other offsets |
| m4 | `ProfileScreen.kt` | Error message shown as inline text (can be scrolled off screen) |
| m5 | `ChronicConditionsScreen.kt` | Uses `Map<String, Any?>` instead of typed request |
| m6 | `ChronicConditionsScreen.kt` | Deprecated `.capitalize()` |
| m7 | `CommunityHealthScreen.kt` | Same `.capitalize()` deprecation |
| m8 | `TelehealthScreen.kt` | Video call is simulated only (no real WebRTC) |

---

## Recommended Fixes

### Priority 1: Implement the 6 Stub Screens

Each of these needs a real screen that calls the existing API endpoints already defined in `ApiService.kt`:

1. **DashboardScreen** — aggregate view pulling from mood, fitness, nutrition, calendar, medications APIs
2. **FitnessScreen** — CRUD for fitness logs (endpoints: `GET/POST fitness`, `DELETE fitness/{id}`)
3. **LabsScreen** — CRUD for lab results (endpoints: `GET/POST labs`, `DELETE labs/{id}`)
4. **MedicationsScreen** — CRUD for medications (endpoints: `GET/POST medications`, `PUT/DELETE medications/{id}`)
5. **LifestyleScreen** — CRUD for lifestyle entries (endpoints: `GET/POST lifestyle`, `DELETE lifestyle/{id}`)
6. **AIChatScreen** — Chat interface (endpoint: `POST ai/chat`)

### Priority 2: Add Missing Navigation Routes

In `MainTabView.kt`, add to the inner `NavHost` and `MoreScreen`:

```kotlin
// In NavHost:
composable("privacy") { PrivacySettingsScreen(innerNavController) }
composable("chronic") { ChronicConditionsScreen(innerNavController) }

// In MoreScreen:
MoreItem(icon = Icons.Default.Shield, title = "Privacy Settings",
    subtitle = "Data sharing and account", onClick = { innerNavController.navigate("privacy") })
MoreItem(icon = Icons.Default.MonitorHeart, title = "Chronic Conditions",
    subtitle = "Manage chronic conditions", onClick = { innerNavController.navigate("chronic") })
```

### Priority 3: Fix MessagingScreen `isOwn` Bug

```kotlin
// BEFORE (wrong):
val isOwn = msg.senderId == conversation.createdBy

// AFTER (correct):
val currentUserId = KeychainHelper.getUserId(context)?.toIntOrNull()
val isOwn = msg.senderId == currentUserId
```

### Priority 4: Add `@SerializedName` Annotations

Add annotations to all fields in: `FitnessLog`, `LabResult`, `Medication`, `LifestyleEntry`, `LoginResponse`, `RegisterRequest`, `UserSchema`, `UserUpdateRequest`, `FitnessLogRequest`, `FitnessLogResponse`, `MedicationRequest`, `LabResultRequest`, `LifestyleEntryRequest`.

### Priority 5: Fix PATCH → PUT for User Updates

```kotlin
// BEFORE:
@PATCH("users/me")
suspend fun updateUser(@Body updates: UserUpdateRequest): UserSchema

// AFTER:
@PUT("users/me")
suspend fun updateUser(@Body updates: UserUpdateRequest): UserSchema
```

---

*End of Audit Report*
