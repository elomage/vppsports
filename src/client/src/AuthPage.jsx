import { useState } from "react";
import { login } from "./api";
import "./AuthPage.css";

const AuthPage = ({ onAuthenticated }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ type: "idle", message: "" });

  const handleLogin = async (event) => {
    event.preventDefault();
    setLoading(true);
    setStatus({ type: "idle", message: "" });

    try {
      const session = await login(username, password);
      onAuthenticated(session.user);
    } catch (error) {
      setStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Authentication failed",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Sign In</h1>
        <p>Authentication is required to access VPPSport.</p>
        <form onSubmit={handleLogin} className="auth-form">
          <label htmlFor="username">Username</label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
            minLength={3}
            maxLength={64}
            disabled={loading}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={12}
            maxLength={128}
            disabled={loading}
          />
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
        {status.message && (
          <div className={`auth-status is-${status.type}`} role="alert">
            {status.message}
          </div>
        )}
      </div>
    </div>
  );
};

export default AuthPage;
