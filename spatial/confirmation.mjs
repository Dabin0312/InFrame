// The detector runs at 4 Hz. Only a second consecutive observation confirms a track.
// Source detections remain available to the policy, mapper and exported report.
export function trackConfirmation() {
  let previous = new Set(), last = -Infinity, segment;
  return (time, seg, ids) => {
    const current = new Set(ids);
    const consecutive = seg === segment && Math.abs(time - last - .25) < .001;
    const confirmed = consecutive ? new Set(ids.filter(id => previous.has(id))) : new Set();
    previous = current; last = time; segment = seg;
    return confirmed;
  };
}
