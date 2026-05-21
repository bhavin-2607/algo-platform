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

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.replace("/login");
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
