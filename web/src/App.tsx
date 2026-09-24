import { Navigate, Route, HashRouter, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./state/auth";
import LoginPage from "./pages/LoginPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectPage from "./pages/ProjectPage";
import RunPage from "./pages/RunPage";

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { apiKey } = useAuth();
  if (!apiKey) return <Navigate to="/login" replace />;
  return children;
}

function TopBar() {
  const { apiKey, logout } = useAuth();
  return (
    <header className="top-bar">
      <a href="#/projects">pcbpick</a>
      {apiKey && (
        <button className="secondary" onClick={logout}>
          Sign out
        </button>
      )}
    </header>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <TopBar />
        <div className="app-shell">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/projects"
              element={
                <RequireAuth>
                  <ProjectsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId"
              element={
                <RequireAuth>
                  <ProjectPage />
                </RequireAuth>
              }
            />
            <Route
              path="/projects/:projectId/runs/:runId"
              element={
                <RequireAuth>
                  <RunPage />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Routes>
        </div>
      </HashRouter>
    </AuthProvider>
  );
}
