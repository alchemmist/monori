const fs = require("node:fs");

module.exports = async (browser, context) => {
    const tokenFile = process.env.PERF_TOKEN_FILE;
    if (!tokenFile) throw new Error("PERF_TOKEN_FILE is required");

    const { token } = JSON.parse(fs.readFileSync(tokenFile, "utf8"));
    if (typeof token !== "string" || token === "") throw new Error("perf token is missing");

    const target = new URL(context.url);
    const page = await browser.newPage();
    await page.goto(new URL("/login", target.origin).toString(), {
        waitUntil: "domcontentloaded",
    });
    await page.evaluate(
        ({ authenticated, accessToken }) => {
            if (authenticated) localStorage.setItem("monori_token", accessToken);
            else localStorage.removeItem("monori_token");
        },
        { authenticated: target.pathname !== "/login", accessToken: token },
    );
    await page.close();
};
