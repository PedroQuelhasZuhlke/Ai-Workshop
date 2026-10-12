import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { DevUser } from "../api/types";
import { useAuth } from "../state/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [existingKey, setExistingKey] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [issued, setIssued] = useState<DevUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function register() {
    setError(null);
    try {
      setIssued(await api.registerUser(displayName.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function recover() {
    setError(null);
    try {
      setIssued(await api.recoverUser(recoveryCode.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function signInWithKey() {
    if (!existingKey.trim()) return;
    login(existingKey.trim());
    navigate("/projects");
  }

  function continueWithIssued() {
    if (!issued) return;
    login(issued.api_key);
    navigate("/projects");
  }

  if (issued) {
    return (
      <div className="card" style={{ maxWidth: 420, margin: "48px auto" }}>
        <h2>Save your credentials</h2>
        <p className="muted">
          These are shown once. Store them somewhere safe (a password manager). The recovery
          code is the only way to get a new API key if you lose this one, and it works once.
        </p>
        <h4>API key</h4>
        <code style={{ wordBreak: "break-all" }}>{issued.api_key}</code>
        <h4>Recovery code</h4>
        <code style={{ wordBreak: "break-all" }}>{issued.recovery_code}</code>
        <div className="field-row" style={{ marginTop: 16 }}>
          <button onClick={continueWithIssued}>I've saved them, continue</button>
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "48px auto" }}>
      <h2>Sign in</h2>
      <p className="muted">
        No identity provider is wired yet -- register a new engineer account, paste an API
        key you already have, or recover a lost key with your recovery code.
      </p>
      <h4>New account</h4>
      <div className="field-row">
        <input
          placeholder="Your name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <button onClick={register} disabled={!displayName.trim()}>
          Create account
        </button>
      </div>
      <h4>Existing API key</h4>
      <div className="field-row">
        <input
          placeholder="API key"
          value={existingKey}
          onChange={(e) => setExistingKey(e.target.value)}
        />
        <button className="secondary" onClick={signInWithKey}>
          Sign in
        </button>
      </div>
      <h4>Lost your API key?</h4>
      <div className="field-row">
        <input
          placeholder="Recovery code"
          value={recoveryCode}
          onChange={(e) => setRecoveryCode(e.target.value)}
        />
        <button className="secondary" onClick={recover} disabled={!recoveryCode.trim()}>
          Recover
        </button>
      </div>
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}
