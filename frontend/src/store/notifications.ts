import { create } from "zustand";
import { persist } from "zustand/middleware";
import { soundService } from "@/utils/sound";

export interface AppNotification {
  id: string;
  title: string;
  message: string;
  type: "order" | "market" | "error" | "system";
  side?: "BUY" | "SELL";
  timestamp: string; // ISO string
  read: boolean;
}

interface NotificationState {
  notifications: AppNotification[];
  soundEnabled: boolean;
  addNotification: (
    notif: Omit<AppNotification, "id" | "timestamp" | "read"> & { playSound?: boolean }
  ) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  clearAll: () => void;
  toggleSound: () => void;
  setSoundEnabled: (enabled: boolean) => void;
}

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set, get) => ({
      notifications: [],
      soundEnabled: soundService.isEnabled(),

      addNotification: (notif) => {
        const id = `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
        const timestamp = new Date().toISOString();
        const newEntry: AppNotification = {
          id,
          title: notif.title,
          message: notif.message,
          type: notif.type,
          side: notif.side,
          timestamp,
          read: false,
        };

        // Play appropriate sound chime
        if (notif.playSound !== false && get().soundEnabled) {
          if (notif.type === "order") {
            soundService.playOrderChime(notif.side || "BUY");
          } else if (notif.type === "market") {
            const isOpening = notif.title.toUpperCase().includes("OPEN");
            soundService.playMarketBell(isOpening);
          } else if (notif.type === "error") {
            soundService.playAlertSound();
          }
        }

        set((state) => ({
          notifications: [newEntry, ...state.notifications].slice(0, 100), // Cap at 100 entries
        }));
      },

      markAsRead: (id: string) =>
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n
          ),
        })),

      markAllAsRead: () =>
        set((state) => ({
          notifications: state.notifications.map((n) => ({ ...n, read: true })),
        })),

      clearAll: () => set({ notifications: [] }),

      toggleSound: () => {
        const next = !get().soundEnabled;
        soundService.setEnabled(next);
        set({ soundEnabled: next });
      },

      setSoundEnabled: (enabled: boolean) => {
        soundService.setEnabled(enabled);
        set({ soundEnabled: enabled });
      },
    }),
    {
      name: "algo:notification_history",
      partialize: (state) => ({
        notifications: state.notifications,
        soundEnabled: state.soundEnabled,
      }),
    }
  )
);

// Convenience helpers for use throughout the application
export const notifyOrder = (
  side: "BUY" | "SELL",
  symbol: string,
  qty: number | string,
  price?: number | string
) => {
  const priceText = price ? ` @ ₹${Number(price).toLocaleString()}` : "";
  useNotificationStore.getState().addNotification({
    title: `${side} ORDER EXECUTED`,
    message: `${side} ${qty} shares/lots of ${symbol}${priceText}`,
    type: "order",
    side,
  });
};

export const notifyMarket = (status: "OPEN" | "CLOSED", customMessage?: string) => {
  const isOpen = status === "OPEN";
  useNotificationStore.getState().addNotification({
    title: isOpen ? "MARKET OPEN" : "MARKET CLOSED",
    message:
      customMessage ||
      (isOpen
        ? "Indian exchange markets are now open for trading."
        : "Market trading session has closed."),
    type: "market",
  });
};

export const notifyError = (title: string, message: string) => {
  useNotificationStore.getState().addNotification({
    title: title.toUpperCase(),
    message,
    type: "error",
  });
};

export const notifySystem = (title: string, message: string) => {
  useNotificationStore.getState().addNotification({
    title: title.toUpperCase(),
    message,
    type: "system",
  });
};
