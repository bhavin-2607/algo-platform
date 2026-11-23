import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";
import { Eye, EyeOff, MapPin, Locate, Monitor, Key, ShieldCheck } from "lucide-react";
import {
  getAstroSettings,
  saveAstroSettings,
  AstroTimingSettings,
  PRESET_CITIES,
} from "@/utils/astroSettings";

export default function SettingsPage() {
  const { user } = useAuthStore();
  const isAdmin  = user?.role === "admin";
  const qc       = useQueryClient();

  return (
    <Layout>
      <div className="page-header">
        <div>
          <h1 className="page-title">USER PROFILE & SETTINGS</h1>
          <p className="page-sub">Account details, connected broker configuration & Dhan token authentication</p>
        </div>
      </div>
      <div className="settings-board">
        {/* Left Column: User Profile & Security */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <UserProfileCard />
          <DisplayScalingCard />
          <PasswordCard />
          <AstroTimingSettingsCard />
        </div>

        {/* Right Column: Connected Broker & Token Refresh */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <BrokerSettingsSection />
          <TokenRenewalCard qc={qc} />
        </div>
      </div>
    </Layout>
  );
}

function UserProfileCard() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === "admin";

  return (
    <div className="card settings-card">
      <div className="card-header">
        <span className="card-title">USER PROFILE</span>
        <span className={`badge ${isAdmin ? "badge-green" : "badge-gray"}`}>
          {isAdmin ? "ADMINISTRATOR" : "TRADER"}
        </span>
      </div>
      <div style={{ padding: "12px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              background: "var(--green-dim)",
              border: "2px solid var(--green)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--green)",
              fontSize: 18,
              fontWeight: 800,
              flexShrink: 0,
            }}
          >
            {user?.username?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: "var(--text)" }}>
              {user?.username ?? "Trader"}
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              {user?.email || `${user?.username || "trader"}@algo-platform.local`}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
          <div>
            <div className="field-label">ACCOUNT STATUS</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--green)", marginTop: 3 }}>
              ACTIVE TRADING
            </div>
          </div>
          <div>
            <div className="field-label">AUTHENTICATION</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)", marginTop: 3 }}>
              JWT ENCRYPTED
            </div>
          </div>
          <div>
            <div className="field-label">USER ID</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3, fontFamily: "monospace" }}>
              {user?.id ? user.id.slice(0, 16) + "..." : "Local Trader"}
            </div>
          </div>
          <div>
            <div className="field-label">SYSTEM ROLE</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: isAdmin ? "var(--yellow)" : "var(--text)", marginTop: 3 }}>
              {isAdmin ? "SUPER ADMIN" : "STANDARD TRADER"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DisplayScalingCard() {
  const [scale, setScale] = useState(() => localStorage.getItem("display_scale") || "auto");

  function handleSelect(newScale: string) {
    setScale(newScale);
    if (newScale && newScale !== "auto") {
      document.documentElement.dataset.scale = newScale;
    } else {
      delete document.documentElement.dataset.scale;
    }
    localStorage.setItem("display_scale", newScale);
    toast.success(`Display scale updated to ${newScale.toUpperCase()}`);
  }

  const options = [
    { id: "auto", label: "Auto (Recommended)", desc: "Enlarges automatically for 27\" monitors & 4K; 100% standard on laptops/MacBooks." },
    { id: "standard", label: "Standard (100%)", desc: "Native compact scaling ideal for 13\"-16\" MacBook and laptop displays." },
    { id: "large", label: "Large (115%)", desc: "Slightly enlarged text and badges; comfortable for 24\" or 27\" 1080p monitors." },
    { id: "extra-large", label: "Extra Large (122%)", desc: "Ideal for 27\" 1440p (QHD / 2K) monitors from desk viewing distance." },
    { id: "huge", label: "Huge (132%)", desc: "Expanded scaling for 27\" to 32\" 4K ultra-high resolution monitors." },
    { id: "compact", label: "Compact (92%)", desc: "Ultra-dense layout displaying maximum rows and columns on screen." },
  ];

  return (
    <div className="card settings-card">
      <div className="card-header">
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Monitor size={15} style={{ color: "var(--green)" }} />
          <span className="card-title">DISPLAY & MONITOR SCALING</span>
        </div>
        <span className="badge badge-gray" style={{ fontSize: 9 }}>
          {scale.toUpperCase()}
        </span>
      </div>
      <div style={{ padding: "12px 14px" }}>
        <p style={{ fontSize: 11, color: "var(--muted)", marginBottom: 12 }}>
          Configure UI and font scaling for your screen. Auto dynamically enhances text readability on 27" monitors without distorting laptop displays.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {options.map((opt) => {
            const isSelected = scale === opt.id;
            return (
              <div
                key={opt.id}
                onClick={() => handleSelect(opt.id)}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 10,
                  padding: "8px 12px",
                  borderRadius: 4,
                  background: isSelected ? "var(--green-dim)" : "var(--surface2)",
                  border: `1px solid ${isSelected ? "var(--green)" : "var(--border)"}`,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <input
                  type="radio"
                  name="display-scale"
                  checked={isSelected}
                  onChange={() => handleSelect(opt.id)}
                  style={{ marginTop: 3, accentColor: "var(--green)", cursor: "pointer" }}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: isSelected ? "var(--green)" : "var(--text)" }}>
                    {opt.label}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                    {opt.desc}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function TokenRenewalCard({qc}: {qc: any}) {
  const [newToken, setNewToken] = useState("");
  const [showToken, setShow]    = useState(false);
  const [pin, setPin] = useState("");
  const [totpSecret, setTotpSecret] = useState("");
  const [showTotpSetup, setShowTotpSetup] = useState(false);
  const [showPin, setShowPin] = useState(false);
  const [showTotpSecret, setShowTotpSecret] = useState(false);

  const { data } = useQuery({
    queryKey: ["settings-status"],
    queryFn: () => api.get("/settings/status").then(r => r.data),
    refetchInterval: 30_000,
  });
  const dhan = data?.dhan ?? {};

  const updateMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-token", {access_token: newToken}),
    onSuccess: (res: any) => {
      toast.success(res.data?.valid ? "Token updated & verified" : "Token saved (verify failed)");
      qc.invalidateQueries({queryKey:["settings-status"]});
      qc.invalidateQueries({queryKey:["dhan-credentials"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
      qc.invalidateQueries({queryKey:["admin-dhan-ip"]});
      setNewToken("");
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Update failed"),
  });

  const renewMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-renew"),
    onSuccess: (res: any) => {
      toast.success(`Token renewed via ${res.data?.method?.toUpperCase() || "RENEW"} — expires ${res.data?.expires_at ?? "in 24h"}`);
      qc.invalidateQueries({queryKey:["settings-status"]});
      qc.invalidateQueries({queryKey:["dhan-credentials"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
      qc.invalidateQueries({queryKey:["admin-dhan-ip"]});
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Renewal failed"),
  });

  const totpMutation = useMutation({
    mutationFn: () => api.post("/settings/dhan-totp", { pin, totp_secret: totpSecret }),
    onSuccess: (res: any) => {
      toast.success("Fresh Dhan token generated via TOTP successfully");
      qc.invalidateQueries({ queryKey: ["settings-status"] });
      qc.invalidateQueries({ queryKey: ["dhan-credentials"] });
      qc.invalidateQueries({ queryKey: ["dhan-auth-token-status"] });
      qc.invalidateQueries({ queryKey: ["broker-accounts"] });
      qc.invalidateQueries({ queryKey: ["brokers"] });
      qc.invalidateQueries({ queryKey: ["dhan-funds"] });
      qc.invalidateQueries({ queryKey: ["admin-dhan-ip"] });
      setPin("");
      setTotpSecret("");
      setShowTotpSetup(false);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "TOTP token generation failed"),
  });

  return (
    <div className="card settings-card">
      <div className="card-header">
        <span className="card-title">DHAN TOKEN REFRESH</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {dhan.totp_configured && (
            <span className="badge badge-blue" style={{ fontSize: 9 }}>
              TOTP CONFIGURED
            </span>
          )}
          <span className={`badge ${dhan.token_valid ? "badge-green" : "badge-red"}`}>
            {dhan.token_valid ? "CONNECTED" : "NEEDS TOKEN"}
          </span>
        </div>
      </div>
      <div className="token-grid">
        <div>
          <div className="field-label">CLIENT ID</div>
          <div className="token-value">{dhan.client_id_set ? "Saved" : "Missing"}</div>
        </div>
        <div>
          <div className="field-label">ACCESS TOKEN</div>
          <div className="token-value">{dhan.token_set ? (dhan.token_valid ? "Active" : "Expired") : "Missing"}</div>
        </div>
        <div>
          <div className="field-label">AUTO RENEW</div>
          <div className="token-value">7:45 IST</div>
        </div>
        <button
          className="connect-btn"
          onClick={() => renewMutation.mutate()}
          disabled={renewMutation.isPending}
          title={dhan.totp_configured ? "Renew token via TOTP or RenewToken" : "Renew existing active token"}
        >
          {renewMutation.isPending ? "RENEWING..." : (dhan.totp_configured ? "RENEW / GENERATE" : "RENEW 24H")}
        </button>
      </div>

      {/* Manual Access Token Input */}
      <div className="token-update">
        <input
          className="field-input"
          type={showToken ? "text" : "password"}
          value={newToken}
          onChange={e => setNewToken(e.target.value)}
          placeholder="Paste fresh access token from web.dhan.co"
        />
        <button type="button" className="connect-btn" onClick={() => setShow(v => !v)}>
          {showToken ? "HIDE" : "SHOW"}
        </button>
        <button
          className="connect-btn"
          onClick={() => updateMutation.mutate()}
          disabled={!newToken.trim() || updateMutation.isPending}
        >
          {updateMutation.isPending ? "SAVING..." : "SAVE TOKEN"}
        </button>
      </div>

      {/* Automated TOTP Setup Trigger */}
      <div style={{ padding: "0 14px 10px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button
          type="button"
          onClick={() => setShowTotpSetup(v => !v)}
          style={{ fontSize: 11, color: "var(--ba-cyan, #08B6DE)", display: "flex", alignItems: "center", gap: 5, background: "transparent", border: "none", cursor: "pointer", padding: 0 }}
        >
          <Key size={13} />
          <span>{showTotpSetup ? "Hide PIN & TOTP Setup" : (dhan.totp_configured ? "Update Dhan PIN & TOTP Secret" : "Setup Automated Token Generation (PIN + TOTP)")}</span>
        </button>
        {dhan.totp_configured && (
          <span style={{ fontSize: 10, color: "var(--green)", display: "flex", alignItems: "center", gap: 4 }}>
            <ShieldCheck size={12} /> Auto-active
          </span>
        )}
      </div>

      {/* TOTP Setup Drawer */}
      {showTotpSetup && (
        <div style={{ margin: "0 14px 12px", padding: "12px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: 4, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)" }}>
            AUTOMATED ACCESS TOKEN GENERATION (PIN + TOTP)
          </div>
          <div style={{ fontSize: 10, color: "var(--muted)", lineHeight: 1.5 }}>
            Per Dhan API specifications, generating a fresh access token without logging into web.dhan.co requires your 6-digit Dhan PIN and TOTP Authenticator Secret. Once saved, token generation runs hands-free daily.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label className="field-label" style={{ fontSize: 9 }}>6-DIGIT DHAN PIN</label>
              <div style={{ position: "relative" }}>
                <input
                  className="field-input"
                  type={showPin ? "text" : "password"}
                  maxLength={6}
                  value={pin}
                  onChange={e => setPin(e.target.value)}
                  placeholder="e.g. 123456"
                  style={{ fontSize: 12, paddingRight: 30 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPin(v => !v)}
                  style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", background: "transparent", border: "none", cursor: "pointer", color: "var(--muted)" }}
                >
                  {showPin ? <EyeOff size={12} /> : <Eye size={12} />}
                </button>
              </div>
            </div>
            <div>
              <label className="field-label" style={{ fontSize: 9 }}>TOTP SECRET KEY (BASE32)</label>
              <div style={{ position: "relative" }}>
                <input
                  className="field-input"
                  type={showTotpSecret ? "text" : "password"}
                  value={totpSecret}
                  onChange={e => setTotpSecret(e.target.value)}
                  placeholder="Base32 secret from QR code"
                  style={{ fontSize: 12, paddingRight: 30 }}
                />
                <button
                  type="button"
                  onClick={() => setShowTotpSecret(v => !v)}
                  style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", background: "transparent", border: "none", cursor: "pointer", color: "var(--muted)" }}
                >
                  {showTotpSecret ? <EyeOff size={12} /> : <Eye size={12} />}
                </button>
              </div>
            </div>
          </div>
          <button
            type="button"
            className="connect-btn"
            onClick={() => totpMutation.mutate()}
            disabled={!pin.trim() || !totpSecret.trim() || totpMutation.isPending}
            style={{ alignSelf: "flex-start", padding: "6px 14px", fontSize: 11 }}
          >
            {totpMutation.isPending ? "GENERATING TOKEN..." : "SAVE & GENERATE FRESH TOKEN"}
          </button>
        </div>
      )}

      <p className="token-note">
        Generate a token at <a href="https://web.dhan.co" target="_blank" rel="noreferrer">web.dhan.co</a> or automate via PIN + TOTP.
        Renewal runs at 7:45, instruments at 8:00, and risk limits reset at 9:15 IST.
      </p>
    </div>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNext, setShowNext] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const mutation = useMutation({
    mutationFn: () => api.post("/users/me/change-password", {
      current_password: current,
      new_password: next,
    }),
    onSuccess: () => {
      toast.success("Password updated");
      setCurrent("");
      setNext("");
      setConfirm("");
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Could not change password"),
  });

  function submit() {
    if (next.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    if (next !== confirm) {
      toast.error("New passwords do not match");
      return;
    }
    mutation.mutate();
  }

  return (
    <div className="card settings-card">
      <div className="card-header">
        <span className="card-title">PASSWORD & SECURITY</span>
      </div>
      <div style={{ padding: "12px 14px", display: "grid", gap: 8 }}>
        <div>
          <label className="field-label" style={{ marginBottom: 4, fontSize: 10 }}>CURRENT PASSWORD</label>
          <div style={{ position: "relative", width: "100%", maxWidth: 320 }}>
            <input
              className="field-input"
              type={showCurrent ? "text" : "password"}
              value={current}
              onChange={e => setCurrent(e.target.value)}
              placeholder="Current password"
              style={{ padding: "6px 32px 6px 10px", fontSize: 12, height: 32 }}
            />
            <button
              type="button"
              onClick={() => setShowCurrent(v => !v)}
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: "var(--muted)",
                display: "flex",
                alignItems: "center",
                padding: 2,
              }}
              title={showCurrent ? "Hide password" : "Show password"}
            >
              {showCurrent ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </div>

        <div>
          <label className="field-label" style={{ marginBottom: 4, fontSize: 10 }}>NEW PASSWORD</label>
          <div style={{ position: "relative", width: "100%", maxWidth: 320 }}>
            <input
              className="field-input"
              type={showNext ? "text" : "password"}
              value={next}
              onChange={e => setNext(e.target.value)}
              placeholder="At least 8 characters"
              style={{ padding: "6px 32px 6px 10px", fontSize: 12, height: 32 }}
            />
            <button
              type="button"
              onClick={() => setShowNext(v => !v)}
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: "var(--muted)",
                display: "flex",
                alignItems: "center",
                padding: 2,
              }}
              title={showNext ? "Hide password" : "Show password"}
            >
              {showNext ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </div>

        <div>
          <label className="field-label" style={{ marginBottom: 4, fontSize: 10 }}>CONFIRM NEW PASSWORD</label>
          <div style={{ position: "relative", width: "100%", maxWidth: 320 }}>
            <input
              className="field-input"
              type={showConfirm ? "text" : "password"}
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              placeholder="Confirm new password"
              style={{ padding: "6px 32px 6px 10px", fontSize: 12, height: 32 }}
            />
            <button
              type="button"
              onClick={() => setShowConfirm(v => !v)}
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: "var(--muted)",
                display: "flex",
                alignItems: "center",
                padding: 2,
              }}
              title={showConfirm ? "Hide password" : "Show password"}
            >
              {showConfirm ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
        </div>

        <button
          className="connect-btn"
          style={{ justifySelf: "start", padding: "6px 16px", fontSize: 11, height: 32, marginTop: 4 }}
          onClick={submit}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "SAVING" : "UPDATE PASSWORD"}
        </button>

        <p className="token-note" style={{ padding: 0, fontSize: 11, color: "var(--muted)" }}>
          Requires current password. Contact an administrator to reset if forgotten.
        </p>
      </div>
    </div>
  );
}

function AstroTimingSettingsCard() {
  const [settings, setSettings] = useState<AstroTimingSettings>(getAstroSettings);

  const togglePrev = () => {
    const next = { ...settings, includePreviousWeek: !settings.includePreviousWeek };
    setSettings(next);
    saveAstroSettings(next);
    toast.success(`Previous week ${next.includePreviousWeek ? "enabled (audit)" : "hidden"}`);
  };

  const toggleNext = () => {
    const next = { ...settings, includeNextWeek: !settings.includeNextWeek };
    setSettings(next);
    saveAstroSettings(next);
    toast.success(`Next week ${next.includeNextWeek ? "enabled (projections)" : "hidden"}`);
  };

  const handleCityChange = (cityName: string) => {
    const preset = PRESET_CITIES.find((c) => c.name === cityName);
    if (preset) {
      const next = { ...settings, city: preset.name, latitude: preset.lat, longitude: preset.lon };
      setSettings(next);
      saveAstroSettings(next);
      toast.success(`Location set to ${preset.name}`);
    } else {
      const next = { ...settings, city: cityName };
      setSettings(next);
      saveAstroSettings(next);
    }
  };

  const handleDetectLocation = () => {
    if (!navigator.geolocation) {
      toast.error("Geolocation is not supported by your browser");
      return;
    }
    toast.loading("Detecting your location...");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        toast.dismiss();
        const lat = parseFloat(pos.coords.latitude.toFixed(4));
        const lon = parseFloat(pos.coords.longitude.toFixed(4));
        const next = { ...settings, city: "Detected Location", latitude: lat, longitude: lon };
        setSettings(next);
        saveAstroSettings(next);
        toast.success(`Location detected: ${lat}° N, ${lon}° E`);
      },
      (err) => {
        toast.dismiss();
        toast.error(`Could not detect location: ${err.message}`);
      },
      { timeout: 10000 }
    );
  };

  return (
    <div className="card settings-card">
      <div className="card-header">
        <span className="card-title">FINANCIAL ASTROLOGY & CYCLICAL TIMING</span>
        <span className="badge badge-gray">WATCH ONLY</span>
      </div>
      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 14 }}>
        <p style={{ fontSize: 11, color: "var(--muted)", margin: 0, lineHeight: 1.4 }}>
          Configure multi-week market timing blocks and user location preference. Astronomical sunrise and planetary
          motion are calculated for your specific city location to match Kundli applications exactly.
        </p>

        {/* User Location Preference */}
        <div
          style={{
            padding: "12px",
            background: "var(--surface2)",
            borderRadius: 4,
            border: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <MapPin size={14} style={{ color: "var(--ba-cyan)" }} />
              <span style={{ fontSize: 11, fontWeight: 800, color: "var(--text)", textTransform: "uppercase" }}>
                User Location Preference
              </span>
            </div>
            <button
              type="button"
              className="connect-btn"
              onClick={handleDetectLocation}
              style={{ padding: "3px 8px", fontSize: 10, display: "flex", alignItems: "center", gap: 4 }}
              title="Detect current location via browser GPS/IP"
            >
              <Locate size={11} />
              DETECT GPS
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr", gap: 8 }}>
            <div>
              <label style={{ fontSize: 9, color: "var(--muted)", fontWeight: 700, display: "block", marginBottom: 3 }}>
                CITY / PRESET
              </label>
              <select
                className="field-input"
                style={{ width: "100%", height: 30, fontSize: 11, padding: "2px 6px" }}
                value={PRESET_CITIES.some((c) => c.name === settings.city) ? settings.city : "Custom"}
                onChange={(e) => handleCityChange(e.target.value)}
              >
                {PRESET_CITIES.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} ({c.lat.toFixed(2)}°N, {c.lon.toFixed(2)}°E)
                  </option>
                ))}
                <option value="Custom">Custom Coordinates</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: 9, color: "var(--muted)", fontWeight: 700, display: "block", marginBottom: 3 }}>
                LATITUDE (°N)
              </label>
              <input
                type="number"
                step="0.0001"
                className="field-input"
                style={{ width: "100%", height: 30, fontSize: 11, padding: "2px 6px" }}
                value={settings.latitude}
                onChange={(e) => {
                  const val = parseFloat(e.target.value) || 0;
                  const next = { ...settings, latitude: val, city: "Custom" };
                  setSettings(next);
                  saveAstroSettings(next);
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: 9, color: "var(--muted)", fontWeight: 700, display: "block", marginBottom: 3 }}>
                LONGITUDE (°E)
              </label>
              <input
                type="number"
                step="0.0001"
                className="field-input"
                style={{ width: "100%", height: 30, fontSize: 11, padding: "2px 6px" }}
                value={settings.longitude}
                onChange={(e) => {
                  const val = parseFloat(e.target.value) || 0;
                  const next = { ...settings, longitude: val, city: "Custom" };
                  setSettings(next);
                  saveAstroSettings(next);
                }}
              />
            </div>
          </div>

          <div style={{ fontSize: 10, color: "var(--ba-cyan)" }}>
            Active: <strong>{settings.city}</strong> ({settings.latitude}° N, {settings.longitude}° E)
          </div>
        </div>

        {/* Previous Week Toggle */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 12px",
            background: "var(--surface2)",
            borderRadius: 4,
            border: "1px solid var(--border)",
          }}
        >
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
              Include Previous Week (Testing & Audit)
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              Mon–Fri (5 trading days) of preceding week for historical reaction verification.
            </div>
          </div>
          <button
            type="button"
            className="connect-btn"
            style={{
              background: settings.includePreviousWeek ? "var(--ba-cyan)" : "transparent",
              color: settings.includePreviousWeek ? "#000" : "var(--muted)",
              border: `1px solid ${settings.includePreviousWeek ? "var(--ba-cyan)" : "var(--border)"}`,
              minWidth: 70,
              fontWeight: 800,
            }}
            onClick={togglePrev}
          >
            {settings.includePreviousWeek ? "ACTIVE" : "OFF"}
          </button>
        </div>

        {/* Next Week Toggle */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 12px",
            background: "var(--surface2)",
            borderRadius: 4,
            border: "1px solid var(--border)",
          }}
        >
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
              Include Next Week (Cyclical Projections)
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              Mon–Fri (5 trading days) of upcoming week for advance cyclical inflection planning.
            </div>
          </div>
          <button
            type="button"
            className="connect-btn"
            style={{
              background: settings.includeNextWeek ? "var(--ba-cyan)" : "transparent",
              color: settings.includeNextWeek ? "#000" : "var(--muted)",
              border: `1px solid ${settings.includeNextWeek ? "var(--ba-cyan)" : "var(--border)"}`,
              minWidth: 70,
              fontWeight: 800,
            }}
            onClick={toggleNext}
          >
            {settings.includeNextWeek ? "ACTIVE" : "OFF"}
          </button>
        </div>

        <div style={{ fontSize: 10, color: "var(--muted)" }}>
          Note: The active Current Week (Mon–Fri) is always included in the timing strip.
        </div>
      </div>
    </div>
  );
}

// ── Broker Settings Section ───────────────────────────────────────────────────
function BrokerSettingsSection() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ broker:"dhan", client_id:"", access_token:"", paper_trading:false });

  const { data: brokers } = useQuery({
    queryKey: ["brokers"],
    queryFn: () => api.get("/brokers").then(r => r.data),
  });

  const connectMutation = useMutation({
    mutationFn: () => api.post("/brokers", {
      broker: form.broker, client_id: form.client_id,
      paper_trading: form.paper_trading,
    }).then(async (res) => {
      if (!form.paper_trading && form.access_token && form.client_id) {
        await api.post("/settings/dhan-credentials", {
          client_id: form.client_id, access_token: form.access_token,
        });
      }
      return res;
    }),
    onSuccess: () => {
      toast.success("Broker added and verified");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
      setShowForm(false);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed"),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/brokers/${id}`),
    onSuccess: () => {
      toast.success("Removed");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
    },
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.post(`/brokers/${id}/activate`),
    onSuccess: (res: any) => {
      toast.success(res.data?.message || "Broker activated successfully");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
      qc.invalidateQueries({queryKey:["dhan-funds"]});
    },
    onError: (e: any) => toast.error(e.response?.data?.detail || "Failed to activate broker"),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => api.patch(`/brokers/${id}/deactivate`),
    onSuccess: () => {
      toast.success("Deactivated");
      qc.invalidateQueries({queryKey:["brokers"]});
      qc.invalidateQueries({queryKey:["broker-accounts"]});
      qc.invalidateQueries({queryKey:["dhan-auth-token-status"]});
    },
  });

  const visibleBrokers = (brokers ?? []).filter((b: any) => b.broker === "dhan" || b.broker === "paper");

  return (
    <div className="card settings-card">
        <div className="card-header">
          <span className="card-title">CONNECTED BROKERS</span>
          <button className="connect-btn" onClick={() => setShowForm(v=>!v)}>
            {showForm ? "CANCEL" : "+ ADD BROKER"}
          </button>
        </div>

        {showForm && (
          <div style={{padding:"12px 14px 0"}}>
            <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:10}}>
              <div className="field">
                <label className="field-label">CLIENT ID</label>
                <input className="field-input" value={form.client_id}
                  onChange={e=>setForm(f=>({...f, client_id:e.target.value}))}
                  placeholder="Your Dhan Client ID" />
              </div>
              <div className="field">
                <label className="field-label">MODE</label>
                <div style={{display:"flex"}}>
                  {["Paper","Live"].map((m,i)=>(
                    <button key={m} type="button"
                      onClick={()=>setForm(f=>({...f, paper_trading:m==="Paper"}))}
                      style={{
                        flex:1, padding:11, fontFamily:"var(--font)", fontSize:11,
                        cursor:"pointer", border:"1px solid",
                        borderRight:i===0?"none":undefined,
                        background:(form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                          ? m==="Paper"?"rgba(255,208,96,0.15)":"rgba(255,68,102,0.1)" : "transparent",
                        borderColor:(form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                          ? m==="Paper"?"rgba(255,208,96,0.4)":"rgba(255,68,102,0.4)" : "var(--border)",
                        color:(form.paper_trading&&m==="Paper")||(!form.paper_trading&&m==="Live")
                          ? m==="Paper"?"var(--yellow)":"var(--red)" : "var(--muted)",
                      }}>{m.toUpperCase()}</button>
                  ))}
                </div>
              </div>
            </div>
            {!form.paper_trading && (
              <div className="field" style={{marginBottom:10}}>
                <label className="field-label">ACCESS TOKEN</label>
                <input className="field-input" type="password"
                  value={form.access_token}
                  onChange={e=>setForm(f=>({...f, access_token:e.target.value}))}
                  placeholder="Paste access token (eyJ...)" />
              </div>
            )}
            <button className={`auth-btn${connectMutation.isPending?" loading":""}`}
              onClick={()=>connectMutation.mutate()}
              disabled={connectMutation.isPending}
              style={{maxWidth:200, marginBottom:10}}>
              {connectMutation.isPending?"ADDING...":"ADD BROKER ->"}
            </button>
          </div>
        )}

        {visibleBrokers.length === 0 && !showForm && (
          <div style={{padding:"20px 14px", textAlign:"center", color:"var(--muted)", fontSize:12}}>
            No broker connected. Add Dhan to start trading.
          </div>
        )}

        {visibleBrokers.map((b: any) => (
          <BrokerRow key={b.id} broker={b} qc={qc}
            onActivate={()=>activateMutation.mutate(b.id)}
            onRemove={()=>removeMutation.mutate(b.id)}
            onDeactivate={()=>deactivateMutation.mutate(b.id)}
          />
        ))}
    </div>
  );
}

function BrokerRow({ broker: b, onActivate, onRemove, onDeactivate }: any) {
  return (
    <div style={{borderTop:"1px solid var(--border)"}}>
      <div style={{padding:"10px 14px", display:"flex", alignItems:"center", justifyContent:"space-between"}}>
        <div style={{display:"flex", alignItems:"center", gap:14}}>
          <div style={{width:36, height:36, borderRadius:4,
            background:"rgba(0,255,136,0.1)", border:"1px solid rgba(0,255,136,0.3)",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:13, fontWeight:700, color:"var(--green)"}}>
            {b.broker[0].toUpperCase()}
          </div>
          <div>
            <div style={{fontWeight:700, fontSize:13}}>{b.broker.toUpperCase()}</div>
            <div style={{fontSize:11, color:"var(--muted)"}}>Client ID: {b.client_id}</div>
          </div>
        </div>
        <div style={{display:"flex", alignItems:"center", gap:8}}>
          <span className={`badge ${b.paper_trading?"badge-yellow":"badge-green"}`}>
            {b.paper_trading?"PAPER":"LIVE"}
          </span>
          <span className={`badge ${b.is_active?"badge-green":"badge-gray"}`}>
            {b.is_active?"ACTIVE":"INACTIVE"}
          </span>
          {!b.is_active && (
            <button className="auth-btn"
              style={{padding:"5px 12px", fontSize:11, width:"auto"}}
              onClick={onActivate}>
              ACTIVATE
            </button>
          )}
          {b.is_active && (
            <button className="exit-btn"
              style={{padding:"5px 12px", fontSize:10, color:"var(--yellow)", borderColor:"rgba(255,208,96,0.3)"}}
              onClick={onDeactivate}>DEACTIVATE</button>
          )}
          <button className="exit-btn" onClick={onRemove}>REMOVE</button>
        </div>
      </div>
    </div>
  );
}
