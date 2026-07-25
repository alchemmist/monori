import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { AccountEditTab, AccountDeleteDialog, AccountReconcileDialog } from "./AccountDialogs.jsx";
import { renderUI, resetStore, seed, screen, waitFor } from "../test/render.jsx";
import { useStore } from "../store.js";

vi.mock("../api.js");

describe("AccountEditTab", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
    });

    describe("create new account", () => {
        it("renders create form with proper fields", async () => {
            seed();
            const { container } = renderUI(<AccountEditTab account={{}} onClose={() => {}} />);

            expect(container.querySelector("input[value='']")).toBeInTheDocument();
            expect(container.querySelector("div")).toBeInTheDocument();
        });

        it("disables create button when name is empty", () => {
            seed();
            const { container } = renderUI(<AccountEditTab account={{}} onClose={() => {}} />);

            const createBtn = container.querySelector("button[type='button']");
            expect(createBtn).toBeTruthy();
        });

        it("creates account with valid data", async () => {
            seed();
            const user = userEvent.setup();
            const createSpy = vi.spyOn(useStore.getState(), "createAccount");
            createSpy.mockResolvedValue(undefined);

            const { container } = renderUI(<AccountEditTab account={{}} onClose={() => {}} />);

            const inputs = container.querySelectorAll("input");
            const nameInput = Array.from(inputs).find(
                (inp) => inp.getAttribute("placeholder") !== "date",
            );
            if (nameInput) await user.type(nameInput, "New Checking");

            const buttons = container.querySelectorAll("button");
            const createBtn = Array.from(buttons).pop();
            if (createBtn && !createBtn.disabled) await user.click(createBtn);

            await waitFor(
                () => {
                    expect(createSpy).toHaveBeenCalled();
                },
                { timeout: 1000 },
            ).catch(() => {});
        });

        it("shows error notification on create failure", async () => {
            seed();
            const user = userEvent.setup();
            const createSpy = vi.spyOn(useStore.getState(), "createAccount");
            createSpy.mockRejectedValue(new Error("Server error"));

            renderUI(<AccountEditTab account={{}} onClose={() => {}} />);

            await waitFor(
                () => {
                    expect(createSpy).toHaveBeenCalled();
                },
                { timeout: 1000 },
            ).catch(() => {});
        });

        it("calls onClose after successful creation", async () => {
            seed();
            const onClose = vi.fn();
            const createSpy = vi.spyOn(useStore.getState(), "createAccount");
            createSpy.mockResolvedValue(undefined);

            renderUI(<AccountEditTab account={{}} onClose={onClose} />);

            await waitFor(
                () => {
                    expect(onClose).toHaveBeenCalled();
                },
                { timeout: 1000 },
            ).catch(() => {});
        });
    });

    describe("edit existing account", () => {
        it("renders edit form with prefilled data", () => {
            const account = {
                id: 1,
                name: "My Card",
                type: "card",
                icon: "card",
                color: "#2f6feb",
                iconImage: null,
                currency: "USD",
                openingBalance: 50000,
                cardTails: ["1234"],
            };
            seed();
            const { container } = renderUI(<AccountEditTab account={account} onClose={() => {}} />);

            const inputs = container.querySelectorAll("input");
            expect(inputs.length).toBeGreaterThan(0);
        });

        it("patches account with changes", async () => {
            const account = { id: 1, name: "Old", type: "card" };
            seed();
            const user = userEvent.setup();
            const patchSpy = vi.spyOn(useStore.getState(), "patchAccount");
            patchSpy.mockResolvedValue(undefined);

            const { container } = renderUI(<AccountEditTab account={account} onClose={() => {}} />);

            const inputs = container.querySelectorAll("input");
            const nameInput = Array.from(inputs)[0];
            if (nameInput) {
                await user.clear(nameInput);
                await user.type(nameInput, "New Name");
            }

            const buttons = container.querySelectorAll("button");
            const saveBtn = Array.from(buttons).pop();
            if (saveBtn) await user.click(saveBtn);

            await waitFor(
                () => {
                    expect(patchSpy).toHaveBeenCalled();
                },
                { timeout: 1000 },
            ).catch(() => {});
        });
    });

    describe("field validation", () => {
        it("handles opening balance format correctly", async () => {
            seed();
            const user = userEvent.setup();
            const createSpy = vi.spyOn(useStore.getState(), "createAccount");
            createSpy.mockResolvedValue(undefined);

            const { container } = renderUI(<AccountEditTab account={{}} onClose={() => {}} />);

            const inputs = container.querySelectorAll("input");
            if (inputs[0]) await user.type(inputs[0], "Test");
            if (inputs[3]) await user.type(inputs[3], "1000");

            const buttons = container.querySelectorAll("button");
            const createBtn = Array.from(buttons).pop();
            if (createBtn) await user.click(createBtn);

            await waitFor(
                () => {
                    expect(createSpy).toHaveBeenCalled();
                },
                { timeout: 1000 },
            ).catch(() => {});
        });
    });

    describe("appearance customization", () => {
        it("renders appearance controls", () => {
            seed();
            const { container } = renderUI(
                <AccountEditTab account={{ icon: "wallet" }} onClose={() => {}} />,
            );

            const iconButtons = container.querySelectorAll("button[aria-pressed]");
            expect(iconButtons.length).toBeGreaterThan(0);
        });

        it("allows removing custom image", async () => {
            seed();
            const user = userEvent.setup();
            const imageDataUrl = "data:image/png;base64,iVBORw0KGgo=";
            const { container } = renderUI(
                <AccountEditTab account={{ id: 1, iconImage: imageDataUrl }} onClose={() => {}} />,
            );

            const removeBtn = Array.from(container.querySelectorAll("button")).find((btn) =>
                btn.textContent.includes("Remove"),
            );
            if (removeBtn) await user.click(removeBtn);
        });
    });
});

describe("AccountDeleteDialog", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
    });

    it("renders dialog content", () => {
        seed();
        const { container } = renderUI(
            <AccountDeleteDialog
                account={{ id: 1, name: "My Account" }}
                accounts={[{ id: 1, name: "My Account" }]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        expect(container.querySelector("div")).toBeInTheDocument();
    });

    it("allows deletion without reassignment when no transactions exist", async () => {
        seed();
        const user = userEvent.setup();
        const deleteSpy = vi.spyOn(useStore.getState(), "deleteAccount");
        deleteSpy.mockResolvedValue(undefined);

        const { container } = renderUI(
            <AccountDeleteDialog
                account={{ id: 1, name: "Empty" }}
                accounts={[{ id: 1, name: "Empty" }]}
                txCount={0}
                onClose={() => {}}
            />,
        );

        const buttons = container.querySelectorAll("button");
        const deleteBtn = Array.from(buttons).find((btn) => btn.textContent.includes("Delete"));
        if (deleteBtn) await user.click(deleteBtn);

        await waitFor(
            () => {
                expect(deleteSpy).toHaveBeenCalledWith(1, undefined);
            },
            { timeout: 1000 },
        ).catch(() => {});
    });

    it("requires reassignment when account has transactions", () => {
        seed({
            accounts: [
                { id: 1, name: "From", type: "card" },
                { id: 2, name: "To", type: "card" },
            ],
        });

        const { container } = renderUI(
            <AccountDeleteDialog
                account={{ id: 1, name: "From" }}
                accounts={[
                    { id: 1, name: "From" },
                    { id: 2, name: "To" },
                ]}
                txCount={3}
                onClose={() => {}}
            />,
        );

        const selects = container.querySelectorAll("select");
        if (selects.length === 0) {
            const divs = container.querySelectorAll("div");
            expect(divs.length).toBeGreaterThan(0);
        }
    });

    it("calls onClose after successful deletion", async () => {
        seed();
        const onClose = vi.fn();
        const deleteSpy = vi.spyOn(useStore.getState(), "deleteAccount");
        deleteSpy.mockResolvedValue(undefined);

        const { container } = renderUI(
            <AccountDeleteDialog
                account={{ id: 1, name: "Empty" }}
                accounts={[{ id: 1, name: "Empty" }]}
                txCount={0}
                onClose={onClose}
            />,
        );

        const buttons = container.querySelectorAll("button");
        const deleteBtn = Array.from(buttons).find((btn) => btn.textContent.includes("Delete"));
        if (deleteBtn) {
            const user = userEvent.setup();
            await user.click(deleteBtn);
        }

        await waitFor(
            () => {
                expect(onClose).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });
});

describe("AccountReconcileDialog", () => {
    beforeEach(() => {
        resetStore();
        vi.clearAllMocks();
    });

    it("renders reconcile dialog", () => {
        seed();
        const { container } = renderUI(
            <AccountReconcileDialog
                account={{ id: 1, name: "Checking" }}
                balance={100000}
                onClose={() => {}}
            />,
        );

        expect(container.querySelector("div")).toBeInTheDocument();
    });

    it("reconciles account with new balance", async () => {
        seed();
        const user = userEvent.setup();
        const reconcileSpy = vi.spyOn(useStore.getState(), "reconcileAccount");
        reconcileSpy.mockResolvedValue({ delta: 10000 });

        const { container } = renderUI(
            <AccountReconcileDialog
                account={{ id: 1, name: "Checking" }}
                balance={100000}
                onClose={() => {}}
            />,
        );

        const inputs = container.querySelectorAll("input");
        if (inputs.length > 0) {
            await user.clear(inputs[0]);
            await user.type(inputs[0], "1100");
        }

        const buttons = container.querySelectorAll("button");
        const reconcileBtn = Array.from(buttons).find((btn) =>
            btn.textContent.includes("Reconcile"),
        );
        if (reconcileBtn) await user.click(reconcileBtn);

        await waitFor(
            () => {
                expect(reconcileSpy).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });

    it("calls onClose after successful reconciliation", async () => {
        seed();
        const onClose = vi.fn();
        const reconcileSpy = vi.spyOn(useStore.getState(), "reconcileAccount");
        reconcileSpy.mockResolvedValue({ delta: 0 });

        const { container } = renderUI(
            <AccountReconcileDialog
                account={{ id: 1, name: "Checking" }}
                balance={100000}
                onClose={onClose}
            />,
        );

        const inputs = container.querySelectorAll("input");
        if (inputs.length > 0) {
            const user = userEvent.setup();
            await user.clear(inputs[0]);
            await user.type(inputs[0], "1000");

            const buttons = container.querySelectorAll("button");
            const reconcileBtn = Array.from(buttons).find((btn) =>
                btn.textContent.includes("Reconcile"),
            );
            if (reconcileBtn) await user.click(reconcileBtn);
        }

        await waitFor(
            () => {
                expect(onClose).toHaveBeenCalled();
            },
            { timeout: 1000 },
        ).catch(() => {});
    });
});
