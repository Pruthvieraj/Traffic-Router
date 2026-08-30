// route_helpers.js
// =================
// Pure, dependency-free formatting/parsing helpers used by
// templates/click_router.html to turn OSRM's raw maneuver/step data into
// human-readable turn-by-turn directions.
//
// WHY THIS IS A SEPARATE FILE (and not just inline in the template like it
// used to be): everything else in this project has automated test
// coverage (see tests/) except this logic, because it lived inline in a
// Jinja-templated HTML file that a Python test runner can't import. Moving
// the pure functions here — no DOM access, no fetch calls, just inputs to
// outputs — makes them testable with a plain Node script
// (tests/frontend/route_helpers.test.js) with zero new dependencies
// (Node's built-in `node:test` runner), while the app itself loads this
// exact same file via a normal <script> tag, so there's only one copy of
// the logic, not a duplicate kept in sync by hand.
//
// UMD-ish export: attaches everything to `window` in the browser (so the
// rest of click_router.html's inline <script> can keep calling these as
// plain globals, unchanged) and to `module.exports` under Node (for tests).
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    var exported = factory();
    for (var key in exported) {
      if (Object.prototype.hasOwnProperty.call(exported, key)) root[key] = exported[key];
    }
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {

  function stopLabel(idx, total) {
    if (idx === 0) return 'Start';
    if (idx === total - 1) return 'End';
    return `Stop ${idx}`;
  }

  function formatHour(hour) {
    const h = Math.floor(hour) % 24;
    const m = Math.round((hour - Math.floor(hour)) * 60);
    const period = h < 12 ? 'AM' : 'PM';
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}:${String(m).padStart(2, '0')} ${period}`;
  }

  function formatDistance(m) {
    return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
  }

  function ordinal(n) {
    const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
    return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
  }

  function maneuverText(step) {
    const m = step.maneuver || {};
    const name = step.name && step.name.trim() ? step.name : 'the road';
    const mod = m.modifier ? m.modifier.replace('_', ' ') : '';
    switch (m.type) {
      case 'depart':
        return `Head${mod ? ' ' + mod : ''} on ${name}`;
      case 'arrive':
        return `Arrive${mod ? ', destination on the ' + mod : ''}`;
      case 'turn':
      case 'end of road':
        return `Turn ${mod || 'onto'} onto ${name}`;
      case 'merge':
        return `Merge onto ${name}`;
      case 'fork':
        return `Keep ${mod || 'straight'} onto ${name}`;
      case 'ramp':
      case 'on ramp':
      case 'off ramp':
        return `Take the ramp${mod ? ' ' + mod : ''} onto ${name}`;
      case 'roundabout':
      case 'rotary':
        return `Enter the roundabout, take the ${ordinal(m.exit || 1)} exit onto ${name}`;
      case 'exit roundabout':
      case 'exit rotary':
        return `Exit the roundabout onto ${name}`;
      case 'continue':
      case 'new name':
      case 'use lane':
      default:
        return `Continue onto ${name}`;
    }
  }

  function buildDirections(legs, orderedPoints) {
    const lines = []; // {text, dist, isStopMarker, legIdx}
    legs.forEach((leg, legIdx) => {
      const steps = leg.steps || [];
      steps.forEach((step, stepIdx) => {
        const isLastStepOfLeg = stepIdx === steps.length - 1;
        let text;
        if (isLastStepOfLeg) {
          const label = stopLabel(legIdx + 1, orderedPoints.length);
          text = legIdx + 1 === orderedPoints.length - 1 ? 'Arrive at your destination' : `Arrive at ${label}`;
        } else {
          text = maneuverText(step);
        }
        lines.push({ text, dist: step.distance, isStopMarker: isLastStepOfLeg, legIdx });
      });
    });
    return lines;
  }

  return { stopLabel, formatHour, formatDistance, ordinal, maneuverText, buildDirections };
});
