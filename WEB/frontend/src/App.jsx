import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { UnitsProvider } from './context/UnitsContext';
import { ClinicianModeProvider } from './context/ClinicianModeContext';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';

// Lazy-loaded pages — each becomes a separate chunk
const Landing = lazy(() => import('./pages/Landing'));
// Public marketing pages — reachable from both the landing nav and, for signed
// in users, the sidebar. They deliberately live outside <Layout> so a logged
// out visitor can read them.
const Contact = lazy(() => import('./pages/Contact'));
const Help = lazy(() => import('./pages/Help'));
const Investors = lazy(() => import('./pages/Investors'));
// Also the Privacy Policy URL required by App Store Connect and Google Play.
const Privacy = lazy(() => import('./pages/Privacy'));
// Admin console at /minister. Server-side require_admin is the
// real gate; this route simply renders 'not authorised' for everyone else.
const Admin = lazy(() => import('./pages/Admin'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const PromptHub = lazy(() => import('./pages/PromptHub'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Nutrition = lazy(() => import('./pages/Nutrition'));
const Fitness = lazy(() => import('./pages/Fitness'));
const Labs = lazy(() => import('./pages/Labs'));
const Medications = lazy(() => import('./pages/Medications'));
const AIChat = lazy(() => import('./pages/AIChat'));
const Profile = lazy(() => import('./pages/Profile'));
const Capture = lazy(() => import('./pages/Capture'));
const MentalHealth = lazy(() => import('./pages/MentalHealth'));
const CommunityHealth = lazy(() => import('./pages/CommunityHealth'));
const Roles = lazy(() => import('./pages/Roles'));
const Calendar = lazy(() => import('./pages/Calendar'));
const Telehealth = lazy(() => import('./pages/Telehealth'));
const Messaging = lazy(() => import('./pages/Messaging'));
const Insurance = lazy(() => import('./pages/Insurance'));
const Physicians = lazy(() => import('./pages/Physicians'));
const LabCharts = lazy(() => import('./pages/LabCharts'));
const Wellness = lazy(() => import('./pages/Wellness'));
const MealPlanner = lazy(() => import('./pages/MealPlanner'));
const ExercisePlanner = lazy(() => import('./pages/ExercisePlanner'));
const ImageAI = lazy(() => import('./pages/ImageAI'));
const PdfTools = lazy(() => import('./pages/PdfTools'));
const PeritonealDialysis = lazy(() => import('./pages/PeritonealDialysis'));
const Hemodialysis = lazy(() => import('./pages/Hemodialysis'));
const Chemotherapy = lazy(() => import('./pages/Chemotherapy'));
const AdvancedDirectives = lazy(() => import('./pages/AdvancedDirectives'));
const ClinicianDashboard = lazy(() => import('./pages/ClinicianDashboard'));
const DataSharing = lazy(() => import('./pages/DataSharing'));
const EHRCallback = lazy(() => import('./pages/EHRCallback'));
const Notifications = lazy(() => import('./pages/Notifications'));
const ChartDashboard = lazy(() => import('./pages/ChartDashboard'));
const Pharmacy = lazy(() => import('./pages/Pharmacy'));
const Pantry = lazy(() => import('./pages/Pantry'));
const Elimination = lazy(() => import('./pages/Elimination'));
const FDARecalls = lazy(() => import('./pages/FDARecalls'));
const DiseaseSurveillance = lazy(() => import('./pages/DiseaseSurveillance'));
const Facilities = lazy(() => import('./pages/Facilities'));
const TherapySessions = lazy(() => import('./pages/TherapySessions'));
const HealthTrends = lazy(() => import('./pages/HealthTrends'));
const MealsDiary = lazy(() => import('./pages/MealsDiary'));
const NutrientTracking = lazy(() => import('./pages/NutrientTracking'));
const Journal = lazy(() => import('./pages/Journal'));
const Symptoms = lazy(() => import('./pages/Symptoms'));
const Sleep = lazy(() => import('./pages/Sleep'));
const Vitals = lazy(() => import('./pages/Vitals'));
const HealthInsights = lazy(() => import('./pages/HealthInsights'));
const Subscription = lazy(() => import('./pages/Subscription'));

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;
  return user ? children : <Navigate to="/landing" />;
}

export default function App() {
  return (
    <AuthProvider>
      <ClinicianModeProvider>
      <UnitsProvider>
      <ErrorBoundary>
      <Suspense fallback={<div className="loading">Loading...</div>}>
        <Routes>
          <Route path="/landing" element={<Landing />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/help" element={<Help />} />
          <Route path="/investors" element={<Investors />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          {/* Destination of the emailed reset link (?token=…). Same component:
              a token in the query string skips straight to the new-password form. */}
          <Route path="/reset-password" element={<ForgotPassword />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<PromptHub />} />
          <Route path="dashboard" element={<Dashboard />} />
          {/* Console lives at /minister so the dev path matches the production
              app host. /admin redirects for old links. */}
          <Route path="minister" element={<Admin />} />
          <Route path="admin" element={<Navigate to="/minister" replace />} />
          <Route path="nutrition" element={<Nutrition />} />
          <Route path="fitness" element={<Fitness />} />
          <Route path="labs" element={<Labs />} />
          <Route path="medications" element={<Medications />} />
          <Route path="mental-health" element={<MentalHealth />} />
          <Route path="community" element={<CommunityHealth />} />
          <Route path="capture" element={<Capture />} />
          <Route path="profile" element={<Profile />} />
          <Route path="roles" element={<Roles />} />
          <Route path="calendar" element={<Calendar />} />
          <Route path="telehealth" element={<Telehealth />} />
          <Route path="messaging" element={<Messaging />} />
          <Route path="insurance" element={<Insurance />} />
          <Route path="physicians" element={<Physicians />} />
          <Route path="lab-charts" element={<LabCharts />} />
          <Route path="wellness" element={<Wellness />} />
          <Route path="meal-planner" element={<MealPlanner />} />
          <Route path="exercise-planner" element={<ExercisePlanner />} />
          <Route path="image-ai" element={<ImageAI />} />
          <Route path="pdf-tools" element={<PdfTools />} />
          <Route path="peritoneal-dialysis" element={<PeritonealDialysis />} />
          <Route path="hemodialysis" element={<Hemodialysis />} />
          <Route path="chemotherapy" element={<Chemotherapy />} />
          <Route path="advanced-directives" element={<AdvancedDirectives />} />
          <Route path="clinician-dashboard" element={<ClinicianDashboard />} />
          <Route path="data-sharing" element={<DataSharing />} />
          <Route path="ehr/callback" element={<EHRCallback />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="chart-dashboard" element={<ChartDashboard />} />
          <Route path="pharmacy" element={<Pharmacy />} />
          <Route path="pantry" element={<Pantry />} />
          <Route path="elimination" element={<Elimination />} />
          <Route path="ai" element={<AIChat />} />
          <Route path="fda-recalls" element={<FDARecalls />} />
          <Route path="surveillance" element={<DiseaseSurveillance />} />
          <Route path="facilities" element={<Facilities />} />
          <Route path="therapy-history" element={<TherapySessions />} />
          <Route path="health-trends" element={<HealthTrends />} />
          <Route path="meals-diary" element={<MealsDiary />} />
          <Route path="nutrient-tracking" element={<NutrientTracking />} />
          <Route path="journal" element={<Journal />} />
          <Route path="symptoms" element={<Symptoms />} />
          <Route path="sleep" element={<Sleep />} />
          <Route path="vitals" element={<Vitals />} />
          <Route path="insights" element={<HealthInsights />} />
          <Route path="subscription" element={<Subscription />} />
        </Route>
      </Routes>
      </Suspense>
      </ErrorBoundary>
      </UnitsProvider>
      </ClinicianModeProvider>
    </AuthProvider>
  );
}
