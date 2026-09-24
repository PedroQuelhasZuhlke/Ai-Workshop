import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../state/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [existingKey, setExistingKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function register() {
    setError(null);
    try {
      const user = await api.registerUser(displayName.trim());
      login(user.api_key);
      navigate("/projects");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function signInWithKey() {
    if (!existingKey.trim()) return;
    login(existingKey.trim());
    navigate("/projects");
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "48px auto" }}>
      <h2>Sign in</h2>
      <p className="muted">
        No identity provider is wired yet -- register a new engineer account, or
        paste an API key you already have.
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
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}
