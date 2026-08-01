export function mutationGateDemo(value) {
    if (value > 0) {
        return value + 1;
    }
    return value - 1;
}
