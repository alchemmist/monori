import { useState } from "react";
import { useStore } from "../store.js";
import Meadow from "../components/Meadow.jsx";
import "./login.css";

export default function LoginPage() {
    const { login, register } = useStore();
    const [mode, setMode] = useState("login");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        if (busy) return;
        setBusy(true);
        setError(null);
        try {
            if (mode === "register") await register(email, password);
            else await login(email, password);
        } catch (err) {
            setError(String(err.message || err));
        } finally {
            setBusy(false);
        }
    };

    const switchMode = () => {
        setMode((m) => (m === "login" ? "register" : "login"));
        setError(null);
    };

    return (
        <div className="login">
            <div className="login__body">
                <div className="login__brand" title="monori">
                    もの<span>り</span>
                </div>
                <h1 className="login__title">
                    {mode === "login" ? (
                        <>
                            Every ruble
                            <br />
                            in its place.
                        </>
                    ) : (
                        <>
                            Start counting
                            <br />
                            what matters.
                        </>
                    )}
                </h1>
                <form className="login__form" onSubmit={submit}>
                    <input
                        className="login__input"
                        type="email"
                        placeholder="Email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                    />
                    <input
                        className="login__input"
                        type="password"
                        placeholder={
                            mode === "register" ? "Password (min 8 characters)" : "Password"
                        }
                        autoComplete={mode === "register" ? "new-password" : "current-password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        minLength={mode === "register" ? 8 : undefined}
                        required
                    />
                    {error && <div className="login__error">{error}</div>}
                    <button className="login__submit" type="submit" disabled={busy}>
                        {busy ? "…" : mode === "login" ? "Sign in" : "Create account"}
                    </button>
                </form>
                <div className="login__switch">
                    {mode === "login" ? (
                        <>
                            No account?{" "}
                            <button type="button" onClick={switchMode}>
                                Register
                            </button>
                        </>
                    ) : (
                        <>
                            Already have an account?{" "}
                            <button type="button" onClick={switchMode}>
                                Sign in
                            </button>
                        </>
                    )}
                </div>
                <div className="login__made">
                    handcrafted ·{" "}
                    <b>
                        もの<span>り</span>
                    </b>
                </div>
                <div className="login__links">
                    <a href="/docs" target="_blank" rel="noreferrer">
                        Docs
                    </a>
                    <a href="/demo" target="_blank" rel="noreferrer">
                        Demo
                    </a>
                    <a href="https://github.com/alchemmist/monori" target="_blank" rel="noreferrer">
                        GitHub
                    </a>
                </div>
            </div>
            <Meadow />
        </div>
    );
}
