import { useState, type SyntheticEvent } from "react";
import { useLocation, useNavigate, type Location } from "react-router-dom";
import { Eye, EyeSlash } from "@gravity-ui/icons";
import { useStore } from "../store.js";
import Meadow from "../components/Meadow.jsx";
import "./login.css";

/** Which field the server blamed, so the form can point at it. */
const badField = (message: string | null): "email" | "password" | null => {
    if (message == null || message === "") return null;
    if (/email/i.test(message)) return "email";
    if (/password/i.test(message)) return "password";
    return null;
};

function isInternalLocation(value: unknown): value is Location {
    if (value == null || typeof value !== "object") return false;
    return (
        "pathname" in value &&
        typeof value.pathname === "string" &&
        value.pathname.startsWith("/") &&
        !value.pathname.startsWith("//") &&
        "search" in value &&
        typeof value.search === "string" &&
        "hash" in value &&
        typeof value.hash === "string"
    );
}

export default function LoginPage() {
    const { login, register } = useStore();
    const location = useLocation();
    const navigate = useNavigate();
    const [mode, setMode] = useState("login");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const submit = async (e: SyntheticEvent<HTMLFormElement>) => {
        e.preventDefault();
        if (busy) return;
        setBusy(true);
        setError(null);
        try {
            if (mode === "register") await register(email, password);
            else await login(email, password);
            const state = location.state as unknown;
            const from =
                state != null && typeof state === "object" && "from" in state ? state.from : null;
            const destination = isInternalLocation(from)
                ? `${from.pathname}${from.search}${from.hash}`
                : "/budget";
            void navigate(destination, { replace: true });
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setBusy(false);
        }
    };

    const blamed = badField(error);

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
                <form className="login__form" onSubmit={(event) => void submit(event)}>
                    <input
                        className={`login__input${blamed === "email" ? " login__input--bad" : ""}`}
                        type="email"
                        placeholder="Email"
                        aria-invalid={blamed === "email" || undefined}
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                    />
                    <div className="login__password">
                        <input
                            className={`login__input${
                                blamed === "password" ? " login__input--bad" : ""
                            }`}
                            type={showPassword ? "text" : "password"}
                            aria-invalid={blamed === "password" || undefined}
                            placeholder={
                                mode === "register" ? "Password (min 8 characters)" : "Password"
                            }
                            autoComplete={mode === "register" ? "new-password" : "current-password"}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            minLength={mode === "register" ? 8 : undefined}
                            required
                        />
                        <button
                            type="button"
                            className="login__eye"
                            onClick={() => setShowPassword((v) => !v)}
                            title={showPassword ? "Hide password" : "Show password"}
                            aria-label={showPassword ? "Hide password" : "Show password"}
                            aria-pressed={showPassword}
                            tabIndex={-1}
                        >
                            {showPassword ? (
                                <EyeSlash width={16} height={16} />
                            ) : (
                                <Eye width={16} height={16} />
                            )}
                        </button>
                    </div>
                    {error != null && error !== "" && <div className="login__error">{error}</div>}
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
