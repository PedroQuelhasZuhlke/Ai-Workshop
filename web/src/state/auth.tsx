import { createContext, useContext, useState, type ReactNode } from "react";
import { getApiKey, setApiKey } from "../api/client";

interface AuthState {
  apiKey: string | null;
  login: (key: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setKey] = useState<string | null>(getApiKey());

  const login = (key: string) => {
    setApiKey(key);
    setKey(key);
  };
  const logout = () => {
    setApiKey(null);
    setKey(null);
  };

  return <AuthContext.Provider value={{ apiKey, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
