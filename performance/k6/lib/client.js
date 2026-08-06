import http from "k6/http";
import { check, fail } from "k6";

export const BASE_URL = __ENV.BASE_URL || "http://front:8000";
export const PASSWORD = "performance-password";

export function request(method, path, body, token, tags = {}) {
    const params = {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        tags,
    };
    if (body !== undefined) params.headers["Content-Type"] = "application/json";
    const response = http.request(
        method,
        `${BASE_URL}${path}`,
        body === undefined ? null : JSON.stringify(body),
        params,
    );
    check(response, { [`${method} ${path} succeeded`]: (result) => result.status >= 200 && result.status < 300 });
    return response;
}

export function json(response, label) {
    if (response.status < 200 || response.status >= 300) fail(`${label}: ${response.status}`);
    return response.json();
}

export function login(email, required = false) {
    const response = http.post(
        `${BASE_URL}/api/auth/token`,
        { username: email, password: PASSWORD },
        { tags: { operation: "auth" } },
    );
    check(response, { "login succeeded": (result) => result.status === 200 });
    if (response.status !== 200) {
        if (required) fail(`login: ${response.status}`);
        return null;
    }
    return response.json().access_token;
}
