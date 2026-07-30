/** Normalize descriptions for matching a refund to its original purchase.
 * Keep in sync with server/app/routers/transactions.py::_merchant_key. */
export function refundMerchantKey(value) {
    return (
        (value ?? "")
            .toLowerCase()
            .replace(/(^|[^a-zа-яё])(refund|return|возврат)(?=$|[^a-zа-яё])/g, "$1 ")
            .match(/[a-zа-яё]+/g)
            ?.join(" ") ?? ""
    );
}
