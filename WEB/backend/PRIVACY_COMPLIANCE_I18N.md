# ALAFIA Privacy, Compliance & Internationalization Guide

## Table of Contents
1. [Overview](#overview)
2. [HIPAA Compliance](#hipaa-compliance)
3. [GDPR Compliance](#gdpr-compliance)
4. [Multi-Language Support](#multi-language-support)
5. [Privacy Models](#privacy-models)
6. [API Endpoints](#api-endpoints)
7. [Implementation Guide](#implementation-guide)
8. [Testing](#testing)

---

## Overview

ALAFIA implements comprehensive privacy, security, and compliance features to protect sensitive health data and serve a global audience. This system ensures compliance with:

- **HIPAA** (Health Insurance Portability and Accountability Act) - US healthcare data protection
- **GDPR** (General Data Protection Regulation) - EU data protection and privacy
- **General Healthcare Privacy** - Best practices for patient data protection

### Key Features

✅ **Consent Management** - Granular consent tracking with audit trail  
✅ **Data Access Logging** - Complete audit log of who accessed what data and why  
✅ **Right to Data Portability** - GDPR Article 20 - Export all data in machine-readable format  
✅ **Right to be Forgotten** - GDPR Article 17 - Request complete data deletion  
✅ **Privacy Settings** - Granular user control over data usage  
✅ **Multi-Language Support** - 20+ languages including African languages  
✅ **RTL Support** - Right-to-left languages (Arabic, Hebrew, etc.)  

---

## HIPAA Compliance

### Security Rule Requirements

#### Administrative Safeguards
```python
# Minimum necessary access control
DataAccessPurpose.TREATMENT  # Direct patient care
DataAccessPurpose.AI_RECOMMENDATION  # AI-generated insights
DataAccessPurpose.ANALYTICS_AGGREGATED  # Anonymized analytics only
DataAccessPurpose.SUPPORT_REQUEST  # Customer support (limited access)
DataAccessPurpose.SECURITY_AUDIT  # Security investigation
```

#### Technical Safeguards
- **Audit Controls**: All PHI access logged in `data_access_logs` table
- **Access Controls**: Role-based access with purpose tracking
- **Encryption**: Data encrypted at rest (PostgreSQL) and in transit (HTTPS/TLS)
- **Automatic Logoff**: Configurable session timeouts (default: 60 minutes)

#### Physical Safeguards
- Data stored in SOC 2 / ISO 27001 certified data centers (when deployed)
- Geographic data residency preferences supported

### Privacy Rule Requirements

#### Patient Rights
1. **Right of Access** - `/api/v1/privacy/export` - Export all health data
2. **Right to Amend** - Standard CRUD endpoints with versioning
3. **Right to an Accounting of Disclosures** - `/api/v1/privacy/access-logs`
4. **Right to Request Restrictions** - Privacy settings control data sharing
5. **Right to Confidential Communications** - End-to-end encryption support

#### Uses and Disclosures
```python
# Consent required for:
ConsentType.DATA_SHARING_ANONYMIZED  # Collective insights (opt-in)
ConsentType.DATA_SHARING_RESEARCH  # Research participation (opt-in)
ConsentType.MARKETING_COMMUNICATIONS  # Marketing (opt-in)
ConsentType.THIRD_PARTY_INTEGRATIONS  # Third-party apps (opt-in)

# No consent needed for (HIPAA permitted uses):
# - Treatment (AI recommendations)
# - Payment (subscription management)
# - Healthcare operations (platform improvement)
```

### Breach Notification

```python
# Implementation guideline:
# 1. Detect breach via security monitoring
# 2. Log in data_access_logs with purpose=SECURITY_AUDIT
# 3. Create incident report
# 4. Notify affected users within 60 days (HIPAA requirement)
# 5. If > 500 users affected, notify HHS and media
```

---

## GDPR Compliance

### Legal Basis for Processing

```python
# GDPR Article 6 - Lawful basis
1. Consent - ConsentRecord.consent_granted = True
2. Contract - Account creation, service delivery
3. Legal Obligation - Compliance with health regulations
4. Vital Interests - Emergency health situations
5. Public Interest - Public health monitoring (anonymized)
6. Legitimate Interest - Platform security, fraud prevention
```

### Key GDPR Rights

#### Article 13-14: Right to Information
- Privacy policy clearly explains data processing
- Consent forms include purpose, retention, recipients
- Available in user's language

#### Article 15: Right of Access
```bash
GET /api/v1/privacy/access-logs
# Returns: Who accessed your data, when, and why
```

#### Article 16: Right to Rectification
```bash
PUT /api/v1/users/me
PUT /api/v1/nutrition/{id}
# Standard update endpoints
```

#### Article 17: Right to Erasure (Right to be Forgotten)
```bash
POST /api/v1/privacy/delete-account
# Workflow:
# 1. User requests deletion
# 2. Admin reviews for legal holds
# 3. Approved requests processed within 30 days
# 4. Data anonymized for collective insights (preserves research value)
# 5. User notified of completion
```

#### Article 20: Right to Data Portability
```bash
POST /api/v1/privacy/export
# Returns: Complete export in JSON/CSV format
# Includes: Profile, health data, AI memories, consents, access logs
# Available within 7 days, auto-expires after 30 days
```

#### Article 21: Right to Object
```python
# Privacy settings allow users to object to:
allow_anonymized_analytics = False
allow_collective_insights = False
allow_research_participation = False
allow_marketing_emails = False
```

### Data Protection by Design

#### Privacy Settings (Default Values)
```python
PrivacySettings(
    allow_anonymized_analytics=True,  # Platform improvement
    allow_collective_insights=False,  # Opt-in (GDPR requires explicit consent)
    allow_research_participation=False,  # Opt-in
    allow_marketing_emails=False,  # Opt-in (GDPR)
    ai_coaching_enabled=True,  # Core feature
    gdpr_applies=True,  # Auto-detected based on country
)
```

#### Consent Management
```python
# GDPR Article 7 - Conditions for consent
# - Freely given (no penalty for withdrawal)
# - Specific (granular consent types)
# - Informed (full consent text stored)
# - Unambiguous (explicit action required)
# - Withdrawable (consent_granted can be set to False)
```

### Data Processing Records (Article 30)
```python
# Automatic logging of all processing activities
DataAccessLog(
    user_id=user.id,
    access_type="view_lab_results",
    resource_type="LabResult",
    purpose=DataAccessPurpose.TREATMENT,
    accessed_at=datetime.utcnow(),
    ip_address="192.168.1.1",
    accessed_by_system="ai_engine",
)
```

### Breach Notification (Article 33-34)
```python
# GDPR requires notification within 72 hours
# Implementation:
# 1. Detect breach
# 2. Log in data_access_logs
# 3. Notify DPA (Data Protection Authority) within 72 hours
# 4. Notify affected users if high risk
# 5. Document in breach register
```

---

## Multi-Language Support

### Supported Languages

| Code | Language | Native Name | Notes |
|------|----------|-------------|-------|
| en | English | English | Default |
| es | Spanish | Español | |
| fr | French | Français | |
| de | German | Deutsch | |
| pt | Portuguese | Português | |
| ar | Arabic | العربية | RTL support |
| zh | Chinese | 中文 | Simplified |
| hi | Hindi | हिन्दी | |
| ru | Russian | Русский | |
| ja | Japanese | 日本語 | |
| ko | Korean | 한국어 | |
| it | Italian | Italiano | |
| nl | Dutch | Nederlands | |
| pl | Polish | Polski | |
| tr | Turkish | Türkçe | |
| vi | Vietnamese | Tiếng Việt | |
| sw | Swahili | Kiswahili | East Africa |
| yo | Yoruba | Yorùbá | Nigeria |
| ig | Igbo | Igbo | Nigeria |
| ha | Hausa | Hausa | West Africa |

### Backend i18n

#### Translation Model
```python
Translation(
    key="dashboard.welcome_message",
    language_code="es",
    value="¡Bienvenido de nuevo! Aquí está tu resumen de salud.",
    category="ui",
    platform="all",  # web, ios, android, all
    is_machine_translated=False,
    is_verified=True,
)
```

#### API Endpoints
```bash
# Get all translations for a language
GET /api/v1/privacy/translations/es
# Response: {"translations": {"key": "value"}, "is_rtl": false}

# Get supported languages
GET /api/v1/privacy/languages
# Response: [{"code": "es", "name": "Spanish", "nativeName": "Español"}]
```

#### Auto-Detection
```python
from app.services.i18n_service import I18nService

i18n = I18nService(db)

# Detect from Accept-Language header
lang = i18n.detect_language_from_accept_header(request.headers.get("Accept-Language"))
# "en-US,en;q=0.9,es;q=0.8" → "en"
```

### Frontend i18n (React)

#### Setup
```bash
# Install dependencies
npm install i18next react-i18next i18next-browser-languagedetector
```

#### Usage
```jsx
import { useTranslation } from 'react-i18next';

function Dashboard() {
  const { t, i18n } = useTranslation();
  
  return (
    <div>
      <h1>{t('dashboard.title')}</h1>
      <p>{t('dashboard.welcome_message')}</p>
      
      {/* With variables */}
      <p>{t('health.calories_consumed', { count: 1850 })}</p>
      
      {/* Change language */}
      <button onClick={() => i18n.changeLanguage('es')}>
        Español
      </button>
    </div>
  );
}
```

#### Language Switcher Component
```jsx
import LanguageSwitcher from './components/LanguageSwitcher';

<LanguageSwitcher variant="dropdown" />
// or
<LanguageSwitcher variant="grid" />
```

### Mobile i18n

#### iOS (Swift)
```swift
// Localizable.strings files
// en.lproj/Localizable.strings
"dashboard.title" = "Health Dashboard";

// es.lproj/Localizable.strings
"dashboard.title" = "Panel de Salud";

// Usage
Text(NSLocalizedString("dashboard.title", comment: "Dashboard title"))
```

#### Android (Kotlin)
```xml
<!-- res/values/strings.xml -->
<string name="dashboard_title">Health Dashboard</string>

<!-- res/values-es/strings.xml -->
<string name="dashboard_title">Panel de Salud</string>

<!-- Usage -->
<TextView android:text="@string/dashboard_title" />
```

### RTL (Right-to-Left) Support

```javascript
// Automatic direction switching
import { isRTL, setDocumentDirection } from './i18n';

// Check if current language is RTL
if (isRTL(i18n.language)) {
  document.documentElement.dir = 'rtl';
}

// CSS for RTL
.container {
  /* LTR: padding-left: 20px */
  /* RTL: padding-right: 20px */
  padding-inline-start: 20px;
}
```

---

## Privacy Models

### Database Schema

#### consent_records
```sql
CREATE TABLE consent_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    consent_type VARCHAR(50) NOT NULL,  -- terms, privacy_policy, data_sharing, etc.
    consent_granted BOOLEAN NOT NULL,  -- True=granted, False=withdrawn
    consent_version VARCHAR(50) NOT NULL,  -- Version of document
    consent_text TEXT,  -- Full text of consent
    consent_language VARCHAR(10),  -- Language of consent (ISO 639-1)
    ip_address VARCHAR(45),  -- Audit trail
    user_agent VARCHAR(500),  -- Browser/app info
    granted_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    INDEX idx_user_consent (user_id, consent_type),
    INDEX idx_granted_at (granted_at)
);
```

#### data_access_logs
```sql
CREATE TABLE data_access_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    accessed_by_user_id INTEGER,  -- Admin/support user
    accessed_by_system VARCHAR(100),  -- System component (e.g., "ai_engine")
    access_type VARCHAR(100) NOT NULL,  -- e.g., "view_labs", "export_data"
    resource_type VARCHAR(100) NOT NULL,  -- e.g., "LabResult", "NutritionLog"
    resource_id INTEGER,  -- Specific record ID
    purpose VARCHAR(50) NOT NULL,  -- HIPAA minimum necessary
    data_accessed JSON,  -- Summary of fields accessed (not full data)
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    accessed_at TIMESTAMP NOT NULL,
    INDEX idx_user_access (user_id, accessed_at),
    INDEX idx_purpose (purpose)
);
```

#### data_export_requests
```sql
CREATE TABLE data_export_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,  -- pending, processing, ready, downloaded, expired
    export_format VARCHAR(20),  -- json, csv, pdf
    include_attachments BOOLEAN,
    requested_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP,
    file_path VARCHAR(500),  -- Secure storage path
    file_size_bytes INTEGER,
    download_url VARCHAR(1000),  -- Signed URL with expiration
    downloaded_at TIMESTAMP,
    download_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP,  -- Auto-delete after 7 days
    error_message TEXT,
    INDEX idx_user_status (user_id, status)
);
```

#### data_deletion_requests
```sql
CREATE TABLE data_deletion_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_email VARCHAR(255) NOT NULL,  -- Preserved for audit
    user_full_name VARCHAR(255),
    status VARCHAR(20) NOT NULL,  -- pending, approved, processing, completed, rejected
    reason TEXT,
    requested_at TIMESTAMP NOT NULL,
    reviewed_at TIMESTAMP,
    reviewed_by_user_id INTEGER,  -- Admin reviewer
    approved_at TIMESTAMP,
    completed_at TIMESTAMP,
    retention_required BOOLEAN DEFAULT FALSE,  -- Legal hold
    retention_reason TEXT,
    retention_until TIMESTAMP,
    deletion_log JSON,  -- Record of what was deleted
    anonymization_log JSON,  -- What was anonymized vs deleted
    notes TEXT,
    INDEX idx_status (status),
    INDEX idx_requested_at (requested_at)
);
```

#### privacy_settings
```sql
CREATE TABLE privacy_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    
    -- Data sharing
    allow_anonymized_analytics BOOLEAN DEFAULT TRUE,
    allow_collective_insights BOOLEAN DEFAULT FALSE,
    allow_research_participation BOOLEAN DEFAULT FALSE,
    
    -- Communications
    allow_marketing_emails BOOLEAN DEFAULT FALSE,
    allow_product_updates BOOLEAN DEFAULT TRUE,
    allow_health_reminders BOOLEAN DEFAULT TRUE,
    
    -- AI
    ai_coaching_enabled BOOLEAN DEFAULT TRUE,
    ai_memory_enabled BOOLEAN DEFAULT TRUE,
    ai_explainability_level VARCHAR(20) DEFAULT 'standard',
    
    -- Third-party
    allow_third_party_integrations BOOLEAN DEFAULT FALSE,
    approved_third_parties JSON,
    
    -- Data retention
    data_retention_days INTEGER,
    auto_delete_old_data BOOLEAN DEFAULT FALSE,
    
    -- Security
    require_biometric_auth BOOLEAN DEFAULT FALSE,
    session_timeout_minutes INTEGER DEFAULT 60,
    
    -- Compliance
    gdpr_applies BOOLEAN DEFAULT FALSE,
    hipaa_applies BOOLEAN DEFAULT FALSE,
    data_residency_preference VARCHAR(50),
    
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

#### translations
```sql
CREATE TABLE translations (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) NOT NULL,  -- e.g., "dashboard.welcome_message"
    language_code VARCHAR(10) NOT NULL,  -- ISO 639-1 (en, es, fr, etc.)
    value TEXT NOT NULL,  -- Translated text
    description VARCHAR(500),  -- Context for translators
    category VARCHAR(100),  -- ui, email, notification, ai_response
    platform VARCHAR(20),  -- web, ios, android, all
    version VARCHAR(50) DEFAULT '1.0',
    is_active BOOLEAN DEFAULT TRUE,
    is_machine_translated BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP,
    verified_by VARCHAR(255),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    INDEX idx_key_lang (key, language_code),
    INDEX idx_category (category),
    INDEX idx_active (is_active)
);
```

---

## API Endpoints

### Consent Management

#### Record Consent
```http
POST /api/v1/privacy/consent
Authorization: Bearer {token}
Content-Type: application/json

{
  "consent_type": "data_sharing_anonymized",
  "consent_granted": true,
  "consent_version": "1.0",
  "language": "en"
}
```

#### Get Active Consents
```http
GET /api/v1/privacy/consent
Authorization: Bearer {token}

Response:
[
  {
    "id": 1,
    "consent_type": "data_sharing_anonymized",
    "consent_granted": true,
    "consent_version": "1.0",
    "granted_at": "2024-01-15T10:30:00Z",
    "expires_at": null
  }
]
```

#### Check Consent Status
```http
GET /api/v1/privacy/consent/data_sharing_anonymized/status
Authorization: Bearer {token}

Response:
{
  "has_consent": true,
  "consent_type": "data_sharing_anonymized"
}
```

### Privacy Settings

#### Get Settings
```http
GET /api/v1/privacy/settings
Authorization: Bearer {token}

Response:
{
  "user_id": 1,
  "allow_anonymized_analytics": true,
  "allow_collective_insights": false,
  "allow_research_participation": false,
  "ai_coaching_enabled": true,
  "gdpr_applies": true,
  "hipaa_applies": false
}
```

#### Update Settings
```http
PUT /api/v1/privacy/settings
Authorization: Bearer {token}
Content-Type: application/json

{
  "allow_collective_insights": true,
  "allow_marketing_emails": false,
  "session_timeout_minutes": 30
}
```

### Data Access Logs

```http
GET /api/v1/privacy/access-logs?limit=50
Authorization: Bearer {token}

Response:
[
  {
    "id": 123,
    "access_type": "view_lab_results",
    "resource_type": "LabResult",
    "purpose": "treatment",
    "accessed_at": "2024-01-15T14:30:00Z",
    "ip_address": "192.168.1.1"
  }
]
```

### Data Export (GDPR Article 20)

#### Request Export
```http
POST /api/v1/privacy/export?export_format=json&include_attachments=true
Authorization: Bearer {token}

Response:
{
  "id": 1,
  "status": "ready",
  "export_format": "json",
  "requested_at": "2024-01-15T10:00:00Z",
  "processed_at": "2024-01-15T10:05:23Z",
  "download_url": "/api/v1/privacy/export/1/download",
  "expires_at": "2024-01-22T10:00:00Z",
  "file_size_bytes": 2485760
}
```

#### Check Export Status
```http
GET /api/v1/privacy/export/1
Authorization: Bearer {token}
```

#### Download Export
```http
GET /api/v1/privacy/export/1/download
Authorization: Bearer {token}

Response: application/json file download
```

### Account Deletion (GDPR Article 17)

#### Request Deletion
```http
POST /api/v1/privacy/delete-account
Authorization: Bearer {token}
Content-Type: application/json

{
  "reason": "No longer using the service"
}

Response:
{
  "id": 1,
  "status": "pending",
  "requested_at": "2024-01-15T10:00:00Z",
  "retention_required": false
}
```

#### Check Deletion Status
```http
GET /api/v1/privacy/delete-account/status
Authorization: Bearer {token}

Response:
{
  "id": 1,
  "status": "in_review",
  "requested_at": "2024-01-15T10:00:00Z",
  "reviewed_at": null,
  "completed_at": null
}
```

### Translations

#### Get All Translations for Language
```http
GET /api/v1/privacy/translations/es?category=ui&platform=web

Response:
{
  "language_code": "es",
  "translations": {
    "common.welcome": "Bienvenido",
    "dashboard.title": "Panel de Salud",
    "nav.nutrition": "Nutrición"
  },
  "is_rtl": false
}
```

#### Get Supported Languages
```http
GET /api/v1/privacy/languages
Accept-Language: en-US,en;q=0.9,es;q=0.8

Response:
{
  "supported_languages": [
    {
      "code": "en",
      "name": "English",
      "name_english": "English",
      "is_rtl": false
    },
    {
      "code": "es",
      "name": "Español",
      "name_english": "Spanish",
      "is_rtl": false
    },
    {
      "code": "ar",
      "name": "العربية",
      "name_english": "Arabic",
      "is_rtl": true
    }
  ],
  "preferred_language": "en"
}
```

---

## Implementation Guide

### Backend Setup

1. **Install Dependencies** (already in requirements.txt)
   ```bash
   # No additional packages needed
   ```

2. **Run Migrations**
   ```bash
   docker exec web-backend-1 alembic upgrade head
   ```

3. **Seed Base Translations**
   ```bash
   docker exec web-backend-1 python scripts/seed_translations.py
   ```

4. **Restart Backend**
   ```bash
   docker compose restart backend
   ```

### Frontend Setup

1. **Install i18n Dependencies**
   ```bash
   cd frontend
   npm install i18next react-i18next i18next-browser-languagedetector
   ```

2. **Import i18n Configuration**
   ```jsx
   // src/main.jsx
   import './i18n';  // Initialize before React
   import React from 'react';
   import ReactDOM from 'react-dom/client';
   import App from './App';
   
   ReactDOM.createRoot(document.getElementById('root')).render(
     <React.StrictMode>
       <App />
     </React.StrictMode>
   );
   ```

3. **Use Translations**
   ```jsx
   import { useTranslation } from 'react-i18next';
   
   function MyComponent() {
     const { t } = useTranslation();
     return <h1>{t('dashboard.title')}</h1>;
   }
   ```

### Mobile Setup

#### iOS

1. **Enable Localization**
   - Xcode → Project → Info → Localizations → Add languages
   - Select en, es, fr, ar, etc.

2. **Create Localizable.strings**
   ```swift
   // Fetch from API
   let url = "https://api.alafia.app/api/v1/privacy/translations/en?platform=ios"
   // Store locally
   ```

#### Android

1. **Create resource folders**
   - res/values/ (English)
   - res/values-es/ (Spanish)
   - res/values-fr/ (French)
   - res/values-ar/ (Arabic)

2. **Fetch from API**
   ```kotlin
   val translations = apiClient.getTranslations("en", platform = "android")
   ```

---

## Testing

### Privacy Features

```bash
# Test consent management
curl -X POST http://localhost:8000/api/v1/privacy/consent \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "consent_type": "data_sharing_anonymized",
    "consent_granted": true,
    "consent_version": "1.0"
  }'

# Test data export
curl -X POST http://localhost:8000/api/v1/privacy/export \
  -H "Authorization: Bearer $TOKEN"

# Check access logs
curl http://localhost:8000/api/v1/privacy/access-logs \
  -H "Authorization: Bearer $TOKEN"
```

### i18n Testing

```bash
# Get Spanish translations
curl http://localhost:8000/api/v1/privacy/translations/es

# Test language detection
curl http://localhost:8000/api/v1/privacy/languages \
  -H "Accept-Language: es-MX,es;q=0.9,en;q=0.8"
```

---

## Best Practices

### HIPAA
1. ✅ Log all PHI access with purpose
2. ✅ Use minimum necessary access principle
3. ✅ Encrypt data at rest and in transit
4. ✅ Implement automatic session timeouts
5. ✅ Regular security audits
6. ✅ Business Associate Agreements with vendors
7. ✅ Breach notification procedures

### GDPR
1. ✅ Privacy by design and default
2. ✅ Explicit consent required (opt-in, not opt-out)
3. ✅ Easy consent withdrawal
4. ✅ Data portability (export in <30 days)
5. ✅ Right to be forgotten (delete in <30 days)
6. ✅ Clear privacy notices in user's language
7. ✅ Data Processing Impact Assessments (DPIAs)
8. ✅ Appoint Data Protection Officer (if required)

### i18n
1. ✅ Never hardcode strings
2. ✅ Use translation keys consistently
3. ✅ Support RTL languages
4. ✅ Test with actual native speakers
5. ✅ Provide context for translators
6. ✅ Handle pluralization and gender
7. ✅ Format dates, times, numbers per locale

---

## Next Steps

1. **Complete Mobile i18n** - Add localization to iOS and Android apps
2. **Admin Dashboard** - Create admin UI for managing deletion requests
3. **Automated Exports** - Background job for data exports
4. **Machine Translation** - Integrate Google Translate API for initial translations
5. **Compliance Monitoring** - Dashboard showing compliance metrics
6. **Privacy Policy Generator** - Auto-generate policy in multiple languages
7. **Cookie Consent Banner** - Add cookie consent for web (GDPR ePrivacy)
8. **Data Retention Policies** - Automated cleanup of old data

---

## Support

For questions about privacy, compliance, or i18n:
- Email: privacy@alafia.app
- DPO (Data Protection Officer): dpo@alafia.app
- Security: security@alafia.app

**Last Updated**: February 13, 2026  
**Version**: 1.0
