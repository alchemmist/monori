export default function Wordmark({ size = 23 }) {
    return (
        <span className="wordmark" style={{ fontSize: size }} aria-label="monori">
            もの
            <span className="wordmark__tail">り</span>
        </span>
    );
}
