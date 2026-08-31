import React, { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { UserProfile } from "../types";
import { safeFetchJson } from "../api";

interface AuthContextType {
  user: { uid: string; email: string; displayName: string } | null;
  userProfile: UserProfile | null;
  isAdmin: boolean;
  isApproved: boolean;
  loading: boolean;
  authError: string | null;
  signInWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  regenerateCrawlerToken: () => Promise<string>;
  saveUserSettings: (key: string, data: any) => Promise<void>;
  getUserSettings: (key: string) => Promise<any>;
  refreshLocalProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function generateSecureToken(uid: string): string {
  const prefix = "ft_live";
  const cleanUid = uid.replace(/[^a-zA-Z0-9]/g, "").slice(0, 8);
  const randomPart = Math.random().toString(36).slice(2, 10);
  const timestampPart = Date.now().toString(36).slice(-4);
  return `${prefix}_${cleanUid}_${randomPart}${timestampPart}`;
}

const DEFAULT_LOCAL_USER = {
  uid: "local-standalone-user-01",
  email: "local.admin@footstats.pro",
  displayName: "Trader Local Pro",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<{ uid: string; email: string; displayName: string } | null>(DEFAULT_LOCAL_USER);
  const [userProfile, setUserProfile] = useState<UserProfile | null>({
    uid: "local-standalone-user-01",
    email: "local.admin@footstats.pro",
    displayName: "Trader Local Pro",
    role: "admin",
    status: "approved",
    crawlerToken: "footstats-crawler-live-key-99",
    createdAt: new Date().toISOString(),
    lastLoginAt: new Date().toISOString(),
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const refreshLocalProfile = async () => {
    try {
      const data = await safeFetchJson<{ config: any }>("/api/config");
      if (data?.config?.userProfile) {
        const u = data.config.userProfile;
        setUserProfile({
          uid: "local-standalone-user-01",
          email: "local.admin@footstats.pro",
          displayName: u.displayName || "Trader Local Pro",
          role: "admin",
          status: "approved",
          crawlerToken: u.crawlerToken || "footstats-crawler-live-key-99",
          createdAt: new Date().toISOString(),
          lastLoginAt: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.warn("Usando perfil local padrão em memória.");
    }
  };

  useEffect(() => {
    refreshLocalProfile();
  }, []);

  const signInWithGoogle = async () => {
    // Standalone local mode is always authenticated as Admin
    setUser(DEFAULT_LOCAL_USER);
    setAuthError(null);
  };

  const logout = async () => {
    // In standalone local mode, resetting simply keeps the clean local admin
    console.log("Modo Standalone Local Ativo");
  };

  const regenerateCrawlerToken = async (): Promise<string> => {
    const newToken = generateSecureToken("local");
    setUserProfile((prev) => (prev ? { ...prev, crawlerToken: newToken } : null));
    
    // Save to local config file via API
    await safeFetchJson("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        userProfile: {
          displayName: userProfile?.displayName || "Trader Local Pro",
          role: "admin",
          status: "approved",
          crawlerToken: newToken,
          mode: "local_standalone",
        },
      }),
    });
    
    return newToken;
  };

  const saveUserSettings = async (key: string, data: any) => {
    try {
      localStorage.setItem(`footstats_${key}`, JSON.stringify(data));
      // Also persist to server local config file
      await safeFetchJson("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferences: key === "preferences" ? data : undefined,
          customUserSettings: key !== "preferences" ? { [key]: data } : undefined,
        }),
      });
    } catch (err) {
      console.error(`Erro ao salvar configuração ${key} localmente:`, err);
    }
  };

  const getUserSettings = async (key: string): Promise<any> => {
    try {
      const fromStorage = localStorage.getItem(`footstats_${key}`);
      if (fromStorage) {
        return JSON.parse(fromStorage);
      }
      const data = await safeFetchJson<{ config: any }>("/api/config");
      if (data?.config) {
        if (key === "preferences" && data.config.preferences) {
          return data.config.preferences;
        }
        if (data.config.customUserSettings?.[key]) {
          return data.config.customUserSettings[key];
        }
      }
    } catch (err) {
      console.error(`Erro ao carregar configuração ${key}:`, err);
    }
    return null;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        userProfile,
        isAdmin: true,
        isApproved: true,
        loading,
        authError,
        signInWithGoogle,
        logout,
        regenerateCrawlerToken,
        saveUserSettings,
        getUserSettings,
        refreshLocalProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth deve ser usado dentro de um AuthProvider");
  }
  return context;
}
