import { useEffect, useState } from "react";
import { z } from "zod";

const policy = z.object({ enabled: z.boolean(), ssoOnly: z.boolean().default(false) });

export function useLoginPolicy() {
    const [value, setValue] = useState<z.infer<typeof policy> | "error" | null>(null);
    useEffect(() => {
        const controller = new AbortController();
        void fetch("/api/auth/oidc/status", { signal: controller.signal, cache: "no-store" })
            .then(async (response) => {
                if (!response.ok) throw new Error("Unavailable");
                const result = policy.parse(await response.json());
                if (!controller.signal.aborted) setValue(result);
            })
            .catch(() => {
                if (!controller.signal.aborted) setValue("error");
            });
        return () => controller.abort();
    }, []);
    return value;
}
