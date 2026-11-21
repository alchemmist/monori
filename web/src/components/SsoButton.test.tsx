import { afterEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import SsoButton, { SsoCallback } from "./SsoButton.jsx";

afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    sessionStorage.clear();
});

it("does not offer SSO without a configured provider", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ enabled: false })));
    render(<SsoButton />);
    expect(screen.queryByRole("button")).toBeNull();
});

it("requires a local session to initiate linking", async () => {
    const request = vi.fn().mockResolvedValue(Response.json({ enabled: true }));
    vi.stubGlobal("fetch", request);
    render(<SsoButton link />);
    fireEvent.click(await screen.findByRole("button", { name: "Link SSO to this account" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(1);
});

it("does not exchange an unsolicited callback and scrubs the URL", async () => {
    const request = vi.fn();
    vi.stubGlobal("fetch", request);
    window.history.replaceState(null, "", "/oidc/callback?state=unknown&code=code");
    render(<SsoCallback />);
    expect(await screen.findByRole("alert")).toHaveTextContent("expired");
    expect(window.location.search).toBe("");
    expect(request).not.toHaveBeenCalled();
});
