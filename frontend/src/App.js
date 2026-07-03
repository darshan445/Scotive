import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import { GuestRoute, ProtectedRoute } from "@/components/ProtectedRoute";
import LoginPage from "@/pages/Login";
import RegisterPage from "@/pages/Register";
import ForgotPasswordPage from "@/pages/ForgotPassword";
import ResetPasswordPage from "@/pages/ResetPassword";
import DashboardPage from "@/pages/Dashboard";
import ClientsPage from "@/pages/Clients";
import ClientDetailPage from "@/pages/ClientDetail";
import ReviewQueuePage from "@/pages/ReviewQueue";
import SettingsPage from "@/pages/Settings";

function App() {
    return (
        <div className="App">
            <BrowserRouter>
                <AuthProvider>
                    <Routes>
                        <Route path="/" element={<Navigate to="/dashboard" replace />} />
                        <Route path="/login" element={<GuestRoute><LoginPage /></GuestRoute>} />
                        <Route path="/register" element={<GuestRoute><RegisterPage /></GuestRoute>} />
                        <Route path="/forgot-password" element={<GuestRoute><ForgotPasswordPage /></GuestRoute>} />
                        <Route path="/reset-password" element={<ResetPasswordPage />} />
                        <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
                        <Route path="/clients" element={<ProtectedRoute><ClientsPage /></ProtectedRoute>} />
                        <Route path="/clients/:email" element={<ProtectedRoute><ClientDetailPage /></ProtectedRoute>} />
                        <Route path="/review" element={<ProtectedRoute><ReviewQueuePage /></ProtectedRoute>} />
                        <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
                        <Route path="*" element={<Navigate to="/dashboard" replace />} />
                    </Routes>
                    <Toaster position="top-right" />
                </AuthProvider>
            </BrowserRouter>
        </div>
    );
}

export default App;
