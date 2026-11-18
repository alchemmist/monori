export const signedSplitAmount = (magnitude: number, transactionAmount: number): number =>
    Math.abs(magnitude) * Math.sign(transactionAmount);
