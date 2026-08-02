import { useLayoutEffect } from "react";
import { Navigate } from "react-router-dom";
import { useStore } from "../store.js";

export default function LogoutPage() {
    const logout = useStore((state) => state.logout);

    useLayoutEffect(() => {
        logout();
    }, [logout]);

    return <Navigate to="/welcome" replace />;
}
