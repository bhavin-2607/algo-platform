import axios from "axios";
import { useAuthStore } from "@/store/auth";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshInFlight: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  const refresh = useAuthStore.getState().refreshToken;
  if (!refresh) return Promise.resolve(null);
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post(`${api.defaults.baseURL}/auth/refresh`, { refresh_token: refresh })
      .then((res) => {
        const access = res.data?.access_token as string;
        const nextRefresh = res.data?.refresh_token || refresh;
        if (!access) return null;
        useAuthStore.getState().setTokens(access, nextRefresh);
        return access;
      })
      .catch(() => null)
      .finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const status = err.response?.status;
    const url = err.config?.url || "";
    const isLogin = url.includes("/auth/login") || url.includes("/auth/refresh");
    if (status === 401 && err.config && !isLogin && !err.config._retry) {
      err.config._retry = true;
      const access = await refreshAccessToken();
      if (access) {
        err.config.headers.Authorization = `Bearer ${access}`;
        return api(err.config);
      }
      useAuthStore.getState().logout();
      if (!window.location.pathname.startsWith("/login")) {
        window.location.replace("/login");
      }
    }
    return Promise.reject(err);
  }
);

export const authApi = {
  login:    (email: string, password: string, mfa_token?: string) =>
    api.post("/auth/login", { email, password, mfa_token }),
  register: (email: string, username: string, password: string) =>
    api.post("/auth/register", { email, username, password }),
};

export const userApi = {
  me:             () => api.get("/users/me"),
  updateProfile:  (username: string) => api.patch("/users/me", { username }),
  changePassword: (current_password: string, new_password: string) =>
    api.post("/users/me/change-password", { current_password, new_password }),
};

export const brokerApi = {
  list:       () => api.get("/brokers"),
  connect:    (data: unknown) => api.post("/brokers", data),
  disconnect: (id: string) => api.delete(`/brokers/${id}`),
  activate:   (id: string) => api.post(`/brokers/${id}/activate`),
  positions:  (id: string) => api.get(`/brokers/${id}/positions`),
  funds:      (id: string) => api.get(`/brokers/${id}/funds`),
};

export const strategyApi = {
  list:   () => api.get("/strategies"),
  my:     () => api.get("/strategies/my"),
  assign: (data: unknown) => api.post("/strategies/assign", data),
  start:  (mapId: string) => api.post(`/strategies/${mapId}/start`),
  stop:   (mapId: string) => api.post(`/strategies/${mapId}/stop`),
  remove: (mapId: string) => api.delete(`/strategies/${mapId}`),
};

export const tradesApi = {
  list:    (params?: Record<string, unknown>) => api.get("/trades", { params }),
  summary: () => api.get("/trades/summary"),
};
