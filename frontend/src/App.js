import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useMatch, useNavigate } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import { GuestRoute, ProtectedRoute } from "@/components/ProtectedRoute";
import LoginPage from "@/pages/Login";
import RegisterPage from "@/pages/Register";
import ForgotPasswordPage from "@/pages/ForgotPassword";
import ResetPasswordPage from "@/pages/ResetPassword";
import LandingPage from "@/pages/Landing";
import DashboardPage from "@/pages/Dashboard";
import ClientsPage from "@/pages/Clients";
import ClientDetailPage from "@/pages/ClientDetail";
import ReviewQueuePage from "@/pages/ReviewQueue";
import SettingsPage from "@/pages/Settings";
import { InvoiceDetailDrawer } from "@/components/InvoiceDetailDrawer";
import { notifyWorkspaceRefresh } from "@/lib/workspaceRefresh";
import { navigateToInvoice } from "@/lib/invoiceNavigation";

/** Opens `/invoices/:id` as a modal route so the current page stays mounted. */
export { navigateToInvoice } from "@/lib/invoiceNavigation";

function InvoiceRouteDrawer() {
    const match = useMatch("/invoices/:invoiceId");
    const navigate = useNavigate();
    const location = useLocation();
    const invoiceId = match?.params?.invoiceId;

    if (!invoiceId) return null;

    return (
        <InvoiceDetailDrawer
            invoiceId={invoiceId}
            open
            onClose={() => {
                if (location.state?.backgroundLocation) {
                    navigate(-1);
                } else {
                    navigate("/dashboard", { replace: true });
                }
            }}
            onChanged={() => notifyWorkspaceRefresh()}
        />
    );
}

function AppRoutes() {
    const location = useLocation();
    const background = location.state?.backgroundLocation;

    return (
        <>
            <Routes location={background || location}>
                <Route path="/" element={<GuestRoute><LandingPage /></GuestRoute>} />
                <Route path="/login" element={<GuestRoute><LoginPage /></GuestRoute>} />
                <Route path="/register" element={<GuestRoute><RegisterPage /></GuestRoute>} />
                <Route path="/forgot-password" element={<GuestRoute><ForgotPasswordPage /></GuestRoute>} />
                <Route path="/reset-password" element={<ResetPasswordPage />} />
                <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
                {/* Direct visit / refresh of an invoice URL — dashboard underneath + drawer */}
                <Route path="/invoices/:invoiceId" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
                <Route path="/clients" element={<ProtectedRoute><ClientsPage /></ProtectedRoute>} />
                <Route path="/clients/:email" element={<ProtectedRoute><ClientDetailPage /></ProtectedRoute>} />
                <Route path="/review" element={<ProtectedRoute><ReviewQueuePage /></ProtectedRoute>} />
                <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
            <InvoiceRouteDrawer />
        </>
    );
}

function App() {
    return (
        <div className="App">
            <BrowserRouter>
                <AuthProvider>
                    <AppRoutes />
                    <Toaster position="top-right" />
                </AuthProvider>
            </BrowserRouter>
        </div>
    );
}

export default App;
