import { useEffect, useState } from "react";
import { z } from "zod";

const transactionKey = "monori_oidc_transaction";
const pending = z.object({ transaction: z.string(), link: z.boolean() });

function headers(link: boolean): Record<string, string> {
    const result: Record<string, string> = { "Content-Type": "application/json" };
    if (link) {
        const token = localStorage.getItem("monori_token");
        if (token == null || token === "") throw new Error("Sign in before linking SSO.");
        result["Authorization"] = `Bearer ${token}`;
    }
    return result;
}

async function start(link: boolean) {
    const r = await fetch(`/api/auth/oidc/${link ? "link/" : ""}start`, {
        method: "POST",
        headers: headers(link),
    });
    if (!r.ok) throw new Error("SSO is unavailable.");
    const { url, transaction } = z
        .object({ url: z.url(), transaction: z.string() })
        .parse(await r.json());
    sessionStorage.setItem(transactionKey, JSON.stringify({ transaction, link }));
    window.location.assign(url);
}

export default function SsoButton({ link = false }: { link?: boolean }) {
    const [enabled, setEnabled] = useState(false);
    const [error, setError] = useState(false);
    useEffect(() => {
        void fetch("/api/auth/oidc/status")
            .then(async (r) => {
                if (r.ok)
                    setEnabled(z.object({ enabled: z.boolean() }).parse(await r.json()).enabled);
            })
            .catch(() => {});
    }, []);
    if (!enabled) return null;
    return (
        <div>
            <button
                type="button"
                onClick={() => {
                    void start(link).catch(() => setError(true));
                }}
            >
                {link ? "Link SSO to this account" : "Sign in with SSO"}
            </button>
            {error && <p role="alert">SSO is unavailable. Try again or sign in with a password.</p>}
        </div>
    );
}

async function finish() {
    const query = new URLSearchParams(window.location.search);
    window.history.replaceState(null, "", window.location.pathname);
    const saved = sessionStorage.getItem(transactionKey);
    sessionStorage.removeItem(transactionKey);
    if (saved == null || !query.has("code") || !query.has("state"))
        throw new Error("SSO was cancelled or the request expired.");
    const { link, transaction } = pending.parse(JSON.parse(saved));
    const r = await fetch(`/api/auth/oidc/${link ? "link/" : ""}finish`, {
        method: "POST",
        headers: headers(link),
        body: JSON.stringify({ transaction, code: query.get("code"), state: query.get("state") }),
    });
    if (!r.ok)
        throw new Error(
            r.status === 409
                ? "Account conflict. For an existing budget, sign in with your password and link SSO in Settings."
                : "SSO verification failed. Please sign in again.",
        );
    const result = z.object({ access_token: z.string() }).parse(await r.json());
    localStorage.setItem("monori_token", result.access_token);
    window.location.replace(link ? "/settings" : "/budget");
}

let completion: Promise<void> | undefined;
export function SsoCallback() {
    const [error, setError] = useState("");
    useEffect(() => {
        completion ??= finish();
        void completion.catch((e: unknown) =>
            setError(e instanceof Error ? e.message : "Sign-in failed."),
        );
    }, []);
    return error ? (
        <main>
            <p role="alert">{error}</p>
            <a href="/login">Return to sign in</a>
        </main>
    ) : (
        <main>Finishing SSO…</main>
    );
}
