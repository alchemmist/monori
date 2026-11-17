export function refundMerchantKey(value: string): string {
    return (
        value
            .toLowerCase()
            .replace(/(?<![a-zа-яё])(refund|return|возврат)(?![a-zа-яё])/g, " ")
            .match(/[a-zа-яё]+/g)
            ?.join(" ") ?? ""
    );
}
