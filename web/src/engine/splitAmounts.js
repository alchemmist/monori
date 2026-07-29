export const signedSplitAmount = (magnitude, transactionAmount) =>
    Math.abs(magnitude) * Math.sign(transactionAmount);
