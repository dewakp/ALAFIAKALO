import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { UnitsProvider } from './context/UnitsContext';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';

// Lazy-loaded pages — each becomes a separate chunk
const Landing = lazy(() => import('./pages/Landing'));
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
const Notifications = lazy(() => import('./pages/Notifications'));
const ChartDashboard = lazy(() => import('./pages/ChartDashboard'));
const Pharmacy = lazy(() => import('./pages/Pharmacy'));
const Pantry = lazy(() => import('./pages/Pantry'));
const Elimination = lazy(() => import('./pages/Elimination'));
const FDARecalls = lazy(() => import('./pages/FDARecalls'));
const TherapySessions = lazy(() => import('./pages/TherapySessions'));
const HealthTrends = lazy(() => import('./pages/HealthTrends'));
const MealsDiary = lazy(() => import('./pages/MealsDiary'));
const NutrientTracking = lazy(() => import('./pages/NutrientTracking'));
const Journal = lazy(() => import('./pages/Journal'));
const Symptoms = lazy(() => import('./pages/Symptoms'));
const Sleep = lazy(() => import('./pages/Sleep'));
const Vitals = lazy(() => import('./pages/Vitals'));
const HealthInsights = lazy(() => import('./pages/HealthInsights'));

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading">Loading...</div>;
  return user ? children : <Navigate to="/landing" />;
}

export default function App() {
  return (
    <AuthProvider>
      <UnitsProvider>
      <ErrorBoundary>
      <Suspense fallback={<div className="loading">Loading...</div>}>
        <Routes>
          <Route path="/landing" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
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
          <Route path="notifications" element={<Notifications />} />
          <Route path="chart-dashboard" element={<ChartDashboard />} />
          <Route path="pharmacy" element={<Pharmacy />} />
          <Route path="pantry" element={<Pantry />} />
          <Route path="elimination" element={<Elimination />} />
          <Route path="ai" element={<AIChat />} />
          <Route path="fda-recalls" element={<FDARecalls />} />
          <Route path="therapy-history" element={<TherapySessions />} />
          <Route path="health-trends" element={<HealthTrends />} />
          <Route path="meals-diary" element={<MealsDiary />} />
          <Route path="nutrient-tracking" element={<NutrientTracking />} />
          <Route path="journal" element={<Journal />} />
          <Route path="symptoms" element={<Symptoms />} />
          <Route path="sleep" element={<Sleep />} />
          <Route path="vitals" element={<Vitals />} />
          <Route path="insights" element={<HealthInsights />} />
        </Route>
      </Routes>
      </Suspense>
      </ErrorBoundary>
      </UnitsProvider>
    </AuthProvider>
  );
}
