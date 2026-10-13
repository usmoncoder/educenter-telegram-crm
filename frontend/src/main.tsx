import "@fontsource-variable/onest";
import "./index.css";

import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router";

import { ApiError } from "./api/client";
import { ToastProvider } from "./components/ui/Toast";
import { Loading } from "./components/ui/Layout";
import { AuthProvider, useAuth } from "./hooks/auth";
import { LangProvider } from "./lib/i18n";
import { AppLayout } from "./layouts/AppLayout";
import { AccountPage, ForbiddenPage, NotFoundPage } from "./pages/Account";
import { AdminsPage } from "./pages/Admins";
import { AuditPage } from "./pages/Audit";
import { AutoReplyPage } from "./pages/AutoReply";
import { CampaignEditorPage } from "./pages/CampaignEditor";
import { CampaignsPage } from "./pages/Campaigns";
import { ConversationDetailPage } from "./pages/ConversationDetail";
import { ConversationsPage } from "./pages/Conversations";
import { CustomerDetailPage, CustomersPage } from "./pages/Customers";
import { DashboardPage } from "./pages/Dashboard";
import { GroupsPage } from "./pages/Groups";
import { HistoryPage } from "./pages/History";
import { IncidentsPage } from "./pages/Incidents";
import { LoginPage } from "./pages/Login";
import { ReportsPage } from "./pages/Reports";
import { SettingsPage } from "./pages/Settings";
import { TelegramPage } from "./pages/Telegram";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: true,
      // Never retry auth/permission/validation failures; retry transient ones once.
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 1,
    },
  },
  mutationCache: new MutationCache(),
});

function RequireAuth() {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  if (!me) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Client-side guard for navigation only; the API enforces every permission server-side. */
function Guard({ perm, children }: { perm: string; children: ReactNode }) {
  const { can } = useAuth();
  return can(perm) ? <>{children}</> : <ForbiddenPage />;
}

const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <Guard perm="dashboard.view"><DashboardPage /></Guard> },
          { path: "incidents", element: <Guard perm="conversations.view"><IncidentsPage /></Guard> },
          { path: "conversations", element: <Guard perm="conversations.view"><ConversationsPage /></Guard> },
          { path: "conversations/:id", element: <Guard perm="conversations.view"><ConversationDetailPage /></Guard> },
          { path: "customers", element: <Guard perm="customers.view"><CustomersPage /></Guard> },
          { path: "customers/:id", element: <Guard perm="customers.view"><CustomerDetailPage /></Guard> },
          { path: "autoreply", element: <Guard perm="autoreply.manage"><AutoReplyPage /></Guard> },
          { path: "groups", element: <Guard perm="groups.view"><GroupsPage /></Guard> },
          { path: "campaigns", element: <Guard perm="campaigns.view"><CampaignsPage /></Guard> },
          { path: "campaigns/new", element: <Guard perm="campaigns.manage"><CampaignEditorPage /></Guard> },
          { path: "campaigns/:id", element: <Guard perm="campaigns.view"><CampaignEditorPage /></Guard> },
          { path: "history", element: <Guard perm="history.view"><HistoryPage /></Guard> },
          { path: "reports", element: <Guard perm="reports.view"><ReportsPage /></Guard> },
          { path: "telegram", element: <Guard perm="telegram.view"><TelegramPage /></Guard> },
          { path: "admins", element: <Guard perm="admins.manage"><AdminsPage /></Guard> },
          { path: "settings", element: <Guard perm="settings.manage"><SettingsPage /></Guard> },
          { path: "audit", element: <Guard perm="audit.view"><AuditPage /></Guard> },
          { path: "account", element: <AccountPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LangProvider>
        <ToastProvider>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </ToastProvider>
      </LangProvider>
    </QueryClientProvider>
  </StrictMode>,
);
