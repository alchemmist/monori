export function refundMerchantKey(value: string): string {
    const words = value.toLowerCase().match(/[a-zа-яё]+/g) ?? [];
    const refundLabels = new Set(["refund", "return", "возврат"]);
    return words.filter((word) => !refundLabels.has(word)).join(" ");
}
