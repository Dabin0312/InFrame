// Fit the tone curve between *corresponding* pixels. Subtract quantization noise
// after applying the curve; appearance and detector inputs retain their colors.
export function visualChange(a, b) {
  if (a === b) return 0;
  const count = new Uint32Array(768), sum = new Float64Array(768);
  for (let i = 0; i < a.length; i++) {
    const k = (i % 3) * 256 + a[i];
    count[k]++; sum[k] += b[i];
  }
  for (let k = 0; k < sum.length; k++) if (count[k]) sum[k] /= count[k];
  let residual = 0;
  for (let i = 0; i < a.length; i++) {
    const predicted = sum[(i % 3) * 256 + a[i]];
    residual += Math.max(0, Math.abs(b[i] - predicted) - 1);
  }
  return residual / a.length;
}
