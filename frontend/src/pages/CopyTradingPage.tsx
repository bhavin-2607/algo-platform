import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/common/Layout";
import { api } from "@/utils/api";
import toast from "react-hot-toast";

interface DhanAccount {
  id: string;
  client_id: string;
  account_role: "MASTER" | "CHILD";
  account_name?: string;
  is_active: boolean;
  is_copy_enabled: boolean;
  paper_trading: boolean;
  fixed_qty_equity: number;
  fixed_lots_fno: number;
  max_loss_limit?: number | null;
  force_market_order: boolean;
  available_margin?: number;
  live_pnl?: number;
  token_valid?: boolean;
  created_at: string;
}

interface CopyTradeLog {
  id: string;
  batch_id: string;
  account_role: string;
  account_name?: string;
  symbol: string;
  exchange: string;
  direction: "BUY" | "SELL";
  order_type: string;
  requested_quantity: number;
  filled_quantity: number;
  fill_price?: number | null;
  broker_order_id?: string | null;
  status: "FILLED" | "REJECTED" | "PENDING" | "SKIPPED";
  error_message?: string | null;
  source: string;
  created_at: string;
}

export default function CopyTradingPage() {
  const qc = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingAccount, setEditingAccount] = useState<DhanAccount | null>(null);

  // Fetch accounts
  const { data: summary, isLoading: accountsLoading } = useQuery({
    queryKey: ["copy-trading-accounts"],
    queryFn: () => api.get("/copy-trading/accounts").then((r) => r.data),
    refetchInterval: 5000,
  });

  // Fetch execution logs
  const { data: logs, isLoading: logsLoading, refetch: refetchLogs } = useQuery({
    queryKey: ["copy-trading-logs"],
    queryFn: () => api.get("/copy-trading/logs?limit=50").then((r) => r.data as CopyTradeLog[]),
    refetchInterval: 3000,
  });

  // Emergency Square Off Mutation
  const squareOffMutation = useMutation({
    mutationFn: () => api.post("/copy-trading/emergency-square-off"),
    onSuccess: (res: any) => {
      toast.success(
        `Emergency square-off completed! ${res.data?.total_orders_placed || 0} exit orders placed.`
      );
      qc.invalidateQueries({ queryKey: ["copy-trading-accounts"] });
      qc.invalidateQueries({ queryKey: ["copy-trading-logs"] });
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || "Emergency square-off failed");
    },
  });

  // Toggle Copy Active Mutation
  const toggleCopyMutation = useMutation({
    mutationFn: ({ id, is_copy_enabled }: { id: string; is_copy_enabled: boolean }) =>
      api.patch(`/copy-trading/accounts/${id}`, { is_copy_enabled }),
    onSuccess: () => {
      toast.success("Copy settings updated");
      qc.invalidateQueries({ queryKey: ["copy-trading-accounts"] });
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || "Failed to update copy status");
    },
  });

  // Delete Account Mutation
  const deleteAccountMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/copy-trading/accounts/${id}`),
    onSuccess: () => {
      toast.success("Account disconnected");
      qc.invalidateQueries({ queryKey: ["copy-trading-accounts"] });
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || "Failed to remove account");
    },
  });

  // Test Connection Mutation
  const testConnMutation = useMutation({
    mutationFn: (id: string) => api.post(`/copy-trading/test-connection/${id}`),
    onSuccess: (res: any) => {
      const data = res.data;
      if (data.status === "success") {
        toast.success(`Connected! Available Margin: ₹${Number(data.available_margin || 0).toLocaleString()} (IP: ${data.ip || "OK"})`);
      } else {
        toast.error(`Connection failed: ${data.message || "Unknown error"}`);
      }
      qc.invalidateQueries({ queryKey: ["copy-trading-accounts"] });
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || "Test connection failed");
    },
  });

  const master: DhanAccount | undefined = summary?.master_account;
  const children: DhanAccount[] = summary?.child_accounts || [];

  return (
    <Layout>
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", width: "100%", flexWrap: "wrap", gap: 14 }}>
          <div>
            <h1 className="page-title" style={{ letterSpacing: 1.5 }}>
              DHAN COPY TRADING HUB
            </h1>
            <p className="page-sub">
              Platform-driven synchronized order fan-out across multiple DhanHQ accounts (Options, Equities, F&O)
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span
              className={`badge ${summary?.active_copy_count ? "badge-green" : "badge-gray"}`}
              style={{ fontSize: 11, padding: "5px 10px", fontWeight: 700 }}
            >
              {summary?.active_copy_count || 0} ACTIVE CHILD ACCOUNTS
            </span>

            {/* Emergency Square Off All Accounts Button */}
            <button
              type="button"
              onClick={() => {
                if (
                  confirm(
                    "EMERGENCY KILL SWITCH: Are you sure you want to cancel all pending orders and MARKET-OUT all open positions across the Master and ALL Child accounts?"
                  )
                ) {
                  squareOffMutation.mutate();
                }
              }}
              disabled={squareOffMutation.isPending}
              style={{
                padding: "8px 16px",
                fontSize: 11,
                fontWeight: 800,
                background: "rgba(255, 40, 80, 0.2)",
                border: "1px solid var(--red)",
                color: "var(--red)",
                borderRadius: 4,
                cursor: "pointer",
                letterSpacing: 0.8,
              }}
              title="Emergency square-off all positions on Master and all Child accounts"
            >
              {squareOffMutation.isPending ? "EXITING ALL ACCOUNTS..." : "EMERGENCY SQUARE OFF ALL"}
            </button>
          </div>
        </div>
      </div>

      {/* MASTER ACCOUNT CARD */}
      <div
        className="card"
        style={{
          marginBottom: 20,
          border: "1px solid rgba(0, 230, 118, 0.3)",
          background: "linear-gradient(180deg, rgba(0,230,118,0.04) 0%, rgba(20,25,35,0.6) 100%)",
        }}
      >
        <div className="card-header" style={{ borderBottom: "1px solid rgba(0, 230, 118, 0.2)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 800, color: "var(--green)", letterSpacing: 1.5 }}>
              PRIMARY MASTER ACCOUNT
            </span>
            <span className="badge badge-green" style={{ fontSize: 9 }}>LEADER / SOURCE</span>
          </div>

          {master && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button
                type="button"
                onClick={() => testConnMutation.mutate(master.id)}
                disabled={testConnMutation.isPending}
                style={{
                  padding: "4px 10px",
                  fontSize: 10,
                  fontWeight: 700,
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  borderRadius: 3,
                  cursor: "pointer",
                }}
              >
                TEST CONNECTION
              </button>
            </div>
          )}
        </div>

        <div style={{ padding: 18 }}>
          {master ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16 }}>
              <div>
                <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1 }}>ACCOUNT NAME</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text)", marginTop: 3 }}>
                  {master.account_name || "Primary Account"}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1 }}>DHAN CLIENT ID</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "var(--green)", marginTop: 3 }}>
                  {master.client_id}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1 }}>MODE</div>
                <div style={{ marginTop: 4 }}>
                  <span className={`badge ${master.paper_trading ? "badge-yellow" : "badge-green"}`}>
                    {master.paper_trading ? "PAPER TRADING" : "LIVE DHAN BROKER"}
                  </span>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1 }}>AVAILABLE MARGIN</div>
                <div style={{ fontSize: 15, fontWeight: 800, color: "#38bdf8", marginTop: 3 }}>
                  ₹{Number(master.available_margin || 0).toLocaleString()}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: 1 }}>CONNECTION STATUS</div>
                <div style={{ marginTop: 4 }}>
                  <span className={`badge ${master.is_active && master.token_valid ? "badge-green" : "badge-red"}`}>
                    {master.is_active && master.token_valid ? "CONNECTED & VALID" : "CHECK CREDENTIALS"}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: "center", color: "var(--muted)", padding: 10, fontSize: 12 }}>
              No Master account registered. Add a Dhan account below and designate it as Master.
            </div>
          )}
        </div>
      </div>

      {/* FOLLOWER / CHILD ACCOUNTS TABLE */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="card-title">CHILD DHAN ACCOUNTS (FOLLOWER EXECUTION)</span>
            <span className="badge badge-gray" style={{ fontSize: 9 }}>{children.length} LINKED</span>
          </div>

          <button
            type="button"
            className="connect-btn"
            onClick={() => {
              setEditingAccount(null);
              setShowAddModal(true);
            }}
            style={{ fontSize: 11, padding: "5px 12px" }}
          >
            + ADD CHILD DHAN ACCOUNT
          </button>
        </div>

        {accountsLoading ? (
          <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
            Loading linked Dhan accounts...
          </div>
        ) : children.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
            No child Dhan accounts connected yet. Click <strong>+ ADD CHILD DHAN ACCOUNT</strong> to link 2 to 5 follower accounts.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: "var(--font)" }}>
              <thead>
                <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                  <th style={{ padding: "10px 8px", textAlign: "center", width: 36, color: "var(--muted)" }}>#</th>
                  <th style={{ padding: "10px 10px", textAlign: "left", color: "var(--muted)" }}>ACCOUNT NAME & CLIENT ID</th>
                  <th style={{ padding: "10px 10px", textAlign: "center", color: "var(--muted)" }}>MODE</th>
                  <th style={{ padding: "10px 10px", textAlign: "center", color: "var(--muted)" }}>COPY STATUS</th>
                  <th style={{ padding: "10px 10px", textAlign: "right", color: "var(--muted)" }}>EQUITY QTY (SHARES)</th>
                  <th style={{ padding: "10px 10px", textAlign: "right", color: "var(--muted)" }}>F&O LOTS</th>
                  <th style={{ padding: "10px 10px", textAlign: "center", color: "var(--muted)" }}>ORDER TYPE</th>
                  <th style={{ padding: "10px 10px", textAlign: "right", color: "var(--muted)" }}>MARGIN</th>
                  <th style={{ padding: "10px 10px", textAlign: "center", color: "var(--muted)" }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {children.map((child, idx) => (
                  <tr key={child.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "10px 8px", textAlign: "center", color: "var(--muted)" }}>
                      {idx + 1}
                    </td>

                    <td style={{ padding: "10px 10px" }}>
                      <div style={{ fontWeight: 700, color: "var(--text)" }}>
                        {child.account_name || `Child Account ${idx + 1}`}
                      </div>
                      <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
                        Client ID: <strong style={{ color: "var(--green)" }}>{child.client_id}</strong>
                      </div>
                    </td>

                    <td style={{ padding: "10px 10px", textAlign: "center" }}>
                      <span className={`badge ${child.paper_trading ? "badge-yellow" : "badge-green"}`}>
                        {child.paper_trading ? "PAPER" : "LIVE"}
                      </span>
                    </td>

                    {/* Copy Active Toggle */}
                    <td style={{ padding: "10px 10px", textAlign: "center" }}>
                      <button
                        type="button"
                        onClick={() =>
                          toggleCopyMutation.mutate({
                            id: child.id,
                            is_copy_enabled: !child.is_copy_enabled,
                          })
                        }
                        style={{
                          padding: "4px 10px",
                          fontSize: 10,
                          fontWeight: 700,
                          borderRadius: 3,
                          cursor: "pointer",
                          background: child.is_copy_enabled ? "rgba(0, 230, 118, 0.16)" : "rgba(255, 255, 255, 0.05)",
                          border: `1px solid ${child.is_copy_enabled ? "var(--green)" : "var(--border)"}`,
                          color: child.is_copy_enabled ? "var(--green)" : "var(--muted)",
                        }}
                        title={child.is_copy_enabled ? "Click to pause copying for this account" : "Click to activate copy trading"}
                      >
                        {child.is_copy_enabled ? "COPY ACTIVE" : "PAUSED"}
                      </button>
                    </td>

                    <td style={{ padding: "10px 10px", textAlign: "right", fontWeight: 700, color: "var(--text)" }}>
                      {child.fixed_qty_equity} shs
                    </td>

                    <td style={{ padding: "10px 10px", textAlign: "right", fontWeight: 700, color: "#38bdf8" }}>
                      {child.fixed_lots_fno} {child.fixed_lots_fno === 1 ? "lot" : "lots"}
                    </td>

                    <td style={{ padding: "10px 10px", textAlign: "center" }}>
                      <span className="badge badge-gray" style={{ fontSize: 9 }}>
                        {child.force_market_order ? "MARKET" : "MATCH MASTER"}
                      </span>
                    </td>

                    <td style={{ padding: "10px 10px", textAlign: "right", fontWeight: 700, color: "#38bdf8" }}>
                      ₹{Number(child.available_margin || 0).toLocaleString()}
                    </td>

                    <td style={{ padding: "10px 10px", textAlign: "center" }}>
                      <div style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                        <button
                          type="button"
                          onClick={() => testConnMutation.mutate(child.id)}
                          style={{
                            padding: "3px 6px",
                            fontSize: 9,
                            fontWeight: 700,
                            background: "transparent",
                            border: "1px solid var(--border)",
                            color: "var(--muted)",
                            borderRadius: 2,
                            cursor: "pointer",
                          }}
                          title="Test Dhan API connection and margin limits"
                        >
                          TEST
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            setEditingAccount(child);
                            setShowAddModal(true);
                          }}
                          style={{
                            padding: "3px 6px",
                            fontSize: 9,
                            fontWeight: 700,
                            background: "transparent",
                            border: "1px solid var(--border)",
                            color: "var(--yellow)",
                            borderRadius: 2,
                            cursor: "pointer",
                          }}
                          title="Edit quantities and settings"
                        >
                          EDIT
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            if (confirm(`Disconnect and remove Dhan account ${child.client_id}?`)) {
                              deleteAccountMutation.mutate(child.id);
                            }
                          }}
                          style={{
                            padding: "3px 6px",
                            fontSize: 9,
                            fontWeight: 700,
                            background: "transparent",
                            border: "1px solid rgba(255, 68, 102, 0.3)",
                            color: "var(--red)",
                            borderRadius: 2,
                            cursor: "pointer",
                          }}
                          title="Remove account"
                        >
                          REMOVE
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* AUDIT LOG: REAL-TIME COPIED EXECUTIONS */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="card-title">COPY EXECUTION AUDIT TRAIL</span>
            <span className="badge badge-gray" style={{ fontSize: 9 }}>REAL-TIME LOG</span>
          </div>

          <button
            type="button"
            onClick={() => refetchLogs()}
            style={{
              padding: "4px 10px",
              fontSize: 10,
              background: "transparent",
              border: "1px solid var(--border)",
              color: "var(--muted)",
              borderRadius: 3,
              cursor: "pointer",
            }}
          >
            REFRESH LOGS
          </button>
        </div>

        {logsLoading ? (
          <div style={{ padding: 30, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
            Loading execution logs...
          </div>
        ) : !logs || logs.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 12 }}>
            No trades executed yet. Place an order in Terminal or Algo Window to view synchronized copy trades.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "var(--font)" }}>
              <thead>
                <tr style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid var(--border)" }}>
                  <th style={{ padding: "8px 8px", textAlign: "left", color: "var(--muted)" }}>TIME</th>
                  <th style={{ padding: "8px 8px", textAlign: "left", color: "var(--muted)" }}>BATCH ID</th>
                  <th style={{ padding: "8px 8px", textAlign: "left", color: "var(--muted)" }}>SYMBOL</th>
                  <th style={{ padding: "8px 8px", textAlign: "center", color: "var(--muted)" }}>SIDE</th>
                  <th style={{ padding: "8px 8px", textAlign: "center", color: "var(--muted)" }}>ROLE</th>
                  <th style={{ padding: "8px 8px", textAlign: "left", color: "var(--muted)" }}>ACCOUNT</th>
                  <th style={{ padding: "8px 8px", textAlign: "right", color: "var(--muted)" }}>QTY</th>
                  <th style={{ padding: "8px 8px", textAlign: "center", color: "var(--muted)" }}>STATUS</th>
                  <th style={{ padding: "8px 8px", textAlign: "right", color: "var(--muted)" }}>PRICE</th>
                  <th style={{ padding: "8px 8px", textAlign: "left", color: "var(--muted)" }}>ORDER ID</th>
                  <th style={{ padding: "8px 8px", textAlign: "center", color: "var(--muted)" }}>SOURCE</th>
                  <th style={{ padding: "8px 8px", textAlign: "left", color: "var(--muted)" }}>NOTES / ERROR</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "8px 8px", color: "var(--muted)" }}>
                      {new Date(log.created_at).toLocaleTimeString()}
                    </td>
                    <td style={{ padding: "8px 8px", color: "var(--text)", fontFamily: "monospace", fontSize: 10 }}>
                      {log.batch_id}
                    </td>
                    <td style={{ padding: "8px 8px", fontWeight: 700, color: "var(--text)" }}>
                      {log.symbol}
                    </td>
                    <td style={{ padding: "8px 8px", textAlign: "center" }}>
                      <span className={`badge ${log.direction === "BUY" ? "badge-green" : "badge-red"}`}>
                        {log.direction}
                      </span>
                    </td>
                    <td style={{ padding: "8px 8px", textAlign: "center" }}>
                      <span className={`badge ${log.account_role === "MASTER" ? "badge-green" : "badge-yellow"}`}>
                        {log.account_role}
                      </span>
                    </td>
                    <td style={{ padding: "8px 8px", color: "var(--text)" }}>
                      {log.account_name || "Account"}
                    </td>
                    <td style={{ padding: "8px 8px", textAlign: "right", fontWeight: 700, color: "var(--text)" }}>
                      {log.requested_quantity}
                    </td>
                    <td style={{ padding: "8px 8px", textAlign: "center" }}>
                      <span className={`badge ${log.status === "FILLED" ? "badge-green" : log.status === "REJECTED" ? "badge-red" : "badge-gray"}`}>
                        {log.status}
                      </span>
                    </td>
                    <td style={{ padding: "8px 8px", textAlign: "right", color: "var(--text)" }}>
                      {log.fill_price ? `₹${Number(log.fill_price).toLocaleString()}` : "—"}
                    </td>
                    <td style={{ padding: "8px 8px", color: "var(--muted)", fontFamily: "monospace", fontSize: 10 }}>
                      {log.broker_order_id || "—"}
                    </td>
                    <td style={{ padding: "8px 8px", textAlign: "center", color: "var(--muted)" }}>
                      {log.source}
                    </td>
                    <td style={{ padding: "8px 8px", color: log.error_message ? "var(--red)" : "var(--muted)", fontSize: 10 }}>
                      {log.error_message || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ADD / EDIT ACCOUNT MODAL */}
      {showAddModal && (
        <AccountModal
          account={editingAccount}
          onClose={() => {
            setShowAddModal(false);
            setEditingAccount(null);
          }}
          onSaved={() => {
            setShowAddModal(false);
            setEditingAccount(null);
            qc.invalidateQueries({ queryKey: ["copy-trading-accounts"] });
          }}
        />
      )}
    </Layout>
  );
}

// ── Modal for Adding / Editing a Dhan Account ────────────────────────────────
function AccountModal({
  account,
  onClose,
  onSaved,
}: {
  account: DhanAccount | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = Boolean(account);
  const [clientId, setClientId] = useState(account?.client_id || "");
  const [token, setToken] = useState("");
  const [accountName, setAccountName] = useState(account?.account_name || "");
  const [role, setRole] = useState<"MASTER" | "CHILD">(account?.account_role || "CHILD");
  const [paperTrading, setPaperTrading] = useState(account?.paper_trading || false);
  const [fixedEquity, setFixedEquity] = useState(account?.fixed_qty_equity || 10);
  const [fixedFno, setFixedFno] = useState(account?.fixed_lots_fno || 1);
  const [forceMarket, setForceMarket] = useState(account?.force_market_order ?? true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!clientId.trim()) {
      toast.error("Client ID is required");
      return;
    }
    if (!isEdit && !token.trim()) {
      toast.error("Access Token is required");
      return;
    }

    setIsSubmitting(true);
    try {
      if (isEdit && account) {
        const payload: any = {
          account_name: accountName,
          account_role: role,
          paper_trading: paperTrading,
          fixed_qty_equity: Number(fixedEquity),
          fixed_lots_fno: Number(fixedFno),
          force_market_order: forceMarket,
        };
        if (token.trim()) {
          payload.access_token = token.trim();
        }
        await api.patch(`/copy-trading/accounts/${account.id}`, payload);
        toast.success("Account settings updated");
      } else {
        await api.post("/copy-trading/accounts", {
          client_id: clientId.trim(),
          access_token: token.trim(),
          account_name: accountName.trim() || `Dhan ${clientId.trim()}`,
          account_role: role,
          paper_trading: paperTrading,
          fixed_qty_equity: Number(fixedEquity),
          fixed_lots_fno: Number(fixedFno),
          force_market_order: forceMarket,
        });
        toast.success("Dhan account linked successfully");
      }
      onSaved();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "Operation failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.75)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        padding: 16,
      }}
    >
      <div
        className="card"
        style={{
          width: "100%",
          maxWidth: 520,
          background: "#141923",
          border: "1px solid var(--border)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
        }}
      >
        <div className="card-header">
          <span className="card-title">
            {isEdit ? "EDIT DHAN ACCOUNT" : "LINK NEW DHAN ACCOUNT"}
          </span>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--muted)",
              cursor: "pointer",
              fontSize: 16,
            }}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div className="field">
              <label className="field-label">ACCOUNT NAME</label>
              <input
                className="field-input"
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                placeholder="e.g. Child 1 - Family"
              />
            </div>

            <div className="field">
              <label className="field-label">CLIENT ID</label>
              <input
                className="field-input"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Dhan Client ID"
                disabled={isEdit}
              />
            </div>
          </div>

          <div className="field" style={{ marginBottom: 12 }}>
            <label className="field-label">
              ACCESS TOKEN {isEdit && <span style={{ color: "var(--muted)", fontSize: 10 }}>(leave empty to keep current)</span>}
            </label>
            <input
              className="field-input"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste token from web.dhan.co"
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div className="field">
              <label className="field-label">ROLE</label>
              <select
                className="field-input"
                value={role}
                onChange={(e) => setRole(e.target.value as any)}
                style={{ background: "#0c1017", color: "var(--text)" }}
              >
                <option value="CHILD">CHILD (FOLLOWER)</option>
                <option value="MASTER">MASTER (LEADER)</option>
              </select>
            </div>

            <div className="field">
              <label className="field-label">MODE</label>
              <select
                className="field-input"
                value={paperTrading ? "paper" : "live"}
                onChange={(e) => setPaperTrading(e.target.value === "paper")}
                style={{ background: "#0c1017", color: "var(--text)" }}
              >
                <option value="live">LIVE DHAN BROKER</option>
                <option value="paper">PAPER TRADING</option>
              </select>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div className="field">
              <label className="field-label">FIXED EQUITY QTY (SHARES)</label>
              <input
                type="number"
                min={1}
                className="field-input"
                value={fixedEquity}
                onChange={(e) => setFixedEquity(Number(e.target.value))}
              />
            </div>

            <div className="field">
              <label className="field-label">FIXED F&O LOTS</label>
              <input
                type="number"
                min={1}
                className="field-input"
                value={fixedFno}
                onChange={(e) => setFixedFno(Number(e.target.value))}
              />
            </div>
          </div>

          <div style={{ marginBottom: 18, display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox"
              id="forceMarket"
              checked={forceMarket}
              onChange={(e) => setForceMarket(e.target.checked)}
              style={{ accentColor: "var(--green)" }}
            />
            <label htmlFor="forceMarket" style={{ fontSize: 11, color: "var(--text)", cursor: "pointer" }}>
              Force MARKET order on follower execution (guarantees fill matching)
            </label>
          </div>

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "8px 16px",
                fontSize: 11,
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--muted)",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              CANCEL
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="connect-btn"
              style={{ padding: "8px 18px", fontSize: 11 }}
            >
              {isSubmitting ? "SAVING..." : isEdit ? "SAVE CHANGES" : "LINK ACCOUNT"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
