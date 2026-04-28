import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { CognitoAuth } from "./cognito";

interface AuthState {
  email: string | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const u = CognitoAuth.instance.currentUser();
      if (!u) {
        setEmail(null);
        return;
      }
      // Validate session by attempting to get a JWT.
      await CognitoAuth.instance.getJwt();
      const e = await CognitoAuth.instance.getEmail();
      setEmail(e || u.getUsername());
    } catch {
      setEmail(null);
    }
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  const signIn = async (e: string, p: string) => {
    await CognitoAuth.instance.signIn(e, p);
    await refresh();
  };
  const signUp = async (e: string, p: string) => {
    await CognitoAuth.instance.signUp(e, p);
    // signUp does not auto-sign-in; pre-signup Lambda auto-confirms whitelisted users.
  };
  const signOut = () => {
    CognitoAuth.instance.signOut();
    setEmail(null);
  };

  return (
    <Ctx.Provider value={{ email, loading, signIn, signUp, signOut, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be inside <AuthProvider>");
  return v;
}
