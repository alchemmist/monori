import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildSnapshot, renderUI, resetStore, screen, setPath, waitFor } from "../test/render.js";
import { useStore } from "../store.js";
import RatesPanel from "./RatesPanel.js";

const refreshRates = vi.fn<ReturnType<typeof useStore.getState>["refreshRates"]>();
const setRate = vi.fn<ReturnType<typeof useStore.getState>["setRate"]>();
const notify = vi.fn<ReturnType<typeof useStore.getState>["notify"]>();

beforeEach(() => {
    resetStore();
    setPath("/settings");
    vi.resetAllMocks();
    refreshRates.mockResolvedValue({ repriced: 2 });
    setRate.mockResolvedValue({ repriced: 1 });
    useStore.setState({
        user: { id: 1, email: "admin@example.com", isAdmin: true },
        snapshot: buildSnapshot({
            baseCurrency: "USD",
            rates: [
                { code: "RUB", rate: 1, day: "2026-03-01", source: "pivot" },
                { code: "USD", rate: 90, day: "2026-02-28", source: "manual", stale: true },
                { code: "XYZ", rate: 5 },
            ],
        }),
        refreshRates,
        setRate,
        notify,
    });
});

afterEach(() => {
    resetStore();
    setPath("/");
});

describe("RatesPanel", () => {
    it("saves a historical row's date and accepts a decimal comma", async () => {
        const { user } = renderUI(<RatesPanel />);
        expect(screen.getByText("as of 2026-02-28")).toBeInTheDocument();
        expect(screen.queryByText("XYZ")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "1.0000 ₽" })).toBeDisabled();
        await user.click(screen.getByRole("button", { name: "90.0000 ₽" }));
        await user.clear(screen.getByRole("textbox"));
        await user.type(screen.getByRole("textbox"), "91,5{Enter}");
        await waitFor(() =>
            expect(setRate).toHaveBeenCalledExactlyOnceWith("USD", 91.5, "2026-02-28"),
        );
        expect(notify).toHaveBeenCalledWith(
            expect.objectContaining({ theme: "success", content: "1 transactions repriced." }),
        );
    });

    it.each(["0", "-5", "wrong", "90", ""])(
        "does not save invalid or unchanged value %j",
        async (value) => {
            const { user } = renderUI(<RatesPanel />);
            await user.click(screen.getByRole("button", { name: "90.0000 ₽" }));
            await user.clear(screen.getByRole("textbox"));
            if (value) await user.type(screen.getByRole("textbox"), value);
            await user.tab();
            expect(setRate).not.toHaveBeenCalled();
        },
    );

    it("cancels an edit with Escape", async () => {
        const { user } = renderUI(<RatesPanel />);
        await user.click(screen.getByRole("button", { name: "90.0000 ₽" }));
        await user.clear(screen.getByRole("textbox"));
        await user.type(screen.getByRole("textbox"), "95{Escape}");
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
        expect(setRate).not.toHaveBeenCalled();
    });

    it.each([false, true])(
        "prevents shared-rate writes for ordinary users or demo (demo=%s)",
        (demo) => {
            if (demo) setPath("/demo");
            else useStore.setState({ user: { id: 2, email: "user@example.com" } });
            renderUI(<RatesPanel />);
            expect(screen.queryByRole("button", { name: "Fetch today" })).not.toBeInTheDocument();
            expect(screen.getByRole("button", { name: "90.0000 ₽" })).toBeDisabled();
        },
    );

    it.each([0, 2])("reports the outcome of a refresh (%s repriced)", async (repriced) => {
        refreshRates.mockResolvedValue({ repriced });
        const { user } = renderUI(<RatesPanel />);
        await user.click(screen.getByRole("button", { name: "Fetch today" }));
        await waitFor(() => expect(refreshRates).toHaveBeenCalledExactlyOnceWith(30));
        expect(notify).toHaveBeenCalledWith(
            expect.objectContaining({
                title: "Rates updated",
                content: repriced ? "2 transactions repriced." : "Nothing needed repricing.",
            }),
        );
    });

    it("reports refresh and override errors without leaving controls disabled", async () => {
        refreshRates.mockRejectedValue(new Error("Feed unavailable"));
        setRate.mockRejectedValue(new Error("Save rejected"));
        const { user } = renderUI(<RatesPanel />);
        await user.click(screen.getByRole("button", { name: "Fetch today" }));
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Could not fetch rates", theme: "danger" }),
            ),
        );
        await user.click(screen.getByRole("button", { name: "90.0000 ₽" }));
        await user.clear(screen.getByRole("textbox"));
        await user.type(screen.getByRole("textbox"), "95{Enter}");
        await waitFor(() =>
            expect(notify).toHaveBeenCalledWith(
                expect.objectContaining({ title: "Could not set the rate", theme: "danger" }),
            ),
        );
        expect(screen.getByRole("button", { name: "90.0000 ₽" })).toBeEnabled();
    });
    it("renders available metadata and saves an undated quote without claiming repricing", async () => {
        setRate.mockResolvedValue({ repriced: 0 });
        useStore.setState({
            snapshot: buildSnapshot({
                rates: [
                    { code: "USD", rate: 90 },
                    { code: "EUR", rate: 95, source: "imported" },
                ],
            }),
        });
        const { user } = renderUI(<RatesPanel />);
        expect(screen.getByText("imported")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "90.0000 ₽" })).toHaveAttribute(
            "title",
            "Set the rate for today by hand",
        );
        await user.click(screen.getByRole("button", { name: "90.0000 ₽" }));
        await user.clear(screen.getByRole("textbox"));
        await user.type(screen.getByRole("textbox"), "91{Enter}");
        await waitFor(() => expect(setRate).toHaveBeenCalledExactlyOnceWith("USD", 91, undefined));
        expect(notify).toHaveBeenCalledWith({ title: "USD set to 91 ₽", theme: "success" });
    });
});
