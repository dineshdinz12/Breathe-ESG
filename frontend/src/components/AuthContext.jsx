import { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../api/client';

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null));
  }, []);

  const login = async (username, password) => {
    await api.csrf();
    const u = await api.login(username, password);
    setUser(u);
  };
  const logout = async () => {
    await api.logout();
    setUser(null);
  };

  return <AuthCtx.Provider value={{ user, login, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
