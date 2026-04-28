import { AuthProvider, useAuth } from "./auth/AuthContext";
import { ConfigProvider } from "./config/ConfigContext";
import { LoginScreen } from "./components/LoginScreen";
import { MainScreen } from "./components/MainScreen";

function Inner() {
  const { email, loading } = useAuth();
  if (loading) {
    return <div className="flex h-screen items-center justify-center text-muted-foreground">Loading…</div>;
  }
  if (!email) {
    return <LoginScreen />;
  }
  return <MainScreen />;
}

export default function App() {
  return (
    <ConfigProvider>
      <AuthProvider>
        <Inner />
      </AuthProvider>
    </ConfigProvider>
  );
}
