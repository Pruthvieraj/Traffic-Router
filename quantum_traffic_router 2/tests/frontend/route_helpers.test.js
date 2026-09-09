// route_helpers.test.js
// ======================
// Tests for static/route_helpers.js — the pure turn-by-turn-directions
// formatting logic used by templates/click_router.html. This is the only
// frontend logic in the project that isn't trivially exercised by the
// Python test suite, so it gets its own tiny, dependency-free test file
// using Node's built-in test runner (no npm install needed — consistent
// with the rest of this project's "zero setup beyond pip install" ethos).
//
// Run with:
//     node --test tests/frontend/
//
// (also run automatically by .github/workflows/tests.yml on every push)

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  stopLabel, formatHour, formatDistance, ordinal, maneuverText, buildDirections,
  advanceSimulatedHour, shouldTriggerIncident, pickIncidentLeg, describeLiveTick,
  fleetOrderChanged,
} = require(path.join(__dirname, '..', '..', 'static', 'route_helpers.js'));

test('stopLabel: Start / End / numbered interior stops', () => {
  assert.equal(stopLabel(0, 4), 'Start');
  assert.equal(stopLabel(3, 4), 'End');
  assert.equal(stopLabel(1, 4), 'Stop 1');
  assert.equal(stopLabel(2, 4), 'Stop 2');
});

test('formatHour: 12-hour clock with AM/PM, including midnight and noon edge cases', () => {
  assert.equal(formatHour(9), '9:00 AM');
  assert.equal(formatHour(18.5), '6:30 PM');
  assert.equal(formatHour(0), '12:00 AM');
  assert.equal(formatHour(12), '12:00 PM');
  assert.equal(formatHour(23.25), '11:15 PM');
});

test('formatDistance: switches from meters to kilometers at 1000m', () => {
  assert.equal(formatDistance(0), '0 m');
  assert.equal(formatDistance(500), '500 m');
  assert.equal(formatDistance(999), '999 m');
  assert.equal(formatDistance(1000), '1.0 km');
  assert.equal(formatDistance(2500), '2.5 km');
});

test('ordinal: standard English ordinal suffix rules, including the 11-13 exception', () => {
  assert.equal(ordinal(1), '1st');
  assert.equal(ordinal(2), '2nd');
  assert.equal(ordinal(3), '3rd');
  assert.equal(ordinal(4), '4th');
  assert.equal(ordinal(11), '11th');
  assert.equal(ordinal(12), '12th');
  assert.equal(ordinal(13), '13th');
  assert.equal(ordinal(21), '21st');
  assert.equal(ordinal(22), '22nd');
});

test('maneuverText: depart, turn, merge, fork, roundabout, arrive', () => {
  assert.equal(maneuverText({ maneuver: { type: 'depart' }, name: 'MG Road' }), 'Head on MG Road');
  assert.equal(
    maneuverText({ maneuver: { type: 'depart', modifier: 'left' }, name: 'MG Road' }),
    'Head left on MG Road',
  );
  assert.equal(
    maneuverText({ maneuver: { type: 'turn', modifier: 'left' }, name: 'Residency Road' }),
    'Turn left onto Residency Road',
  );
  assert.equal(maneuverText({ maneuver: { type: 'merge' }, name: 'Outer Ring Road' }), 'Merge onto Outer Ring Road');
  assert.equal(maneuverText({ maneuver: { type: 'fork', modifier: 'right' }, name: 'NH44' }), 'Keep right onto NH44');
  assert.equal(
    maneuverText({ maneuver: { type: 'roundabout', exit: 2 }, name: 'Trinity Circle' }),
    'Enter the roundabout, take the 2nd exit onto Trinity Circle',
  );
  assert.equal(maneuverText({ maneuver: { type: 'arrive' }, name: '' }), 'Arrive');
  assert.equal(
    maneuverText({ maneuver: { type: 'arrive', modifier: 'right' }, name: '' }),
    'Arrive, destination on the right',
  );
  // unknown/unnamed step falls back sensibly instead of crashing
  assert.equal(maneuverText({ maneuver: {}, name: '' }), 'Continue onto the road');
});

test('buildDirections: flattens OSRM legs into a line list with a stop marker at the end of each leg', () => {
  const legs = [
    {
      steps: [
        { maneuver: { type: 'depart' }, name: 'A Road', distance: 200 },
        { maneuver: { type: 'turn', modifier: 'left' }, name: 'B Road', distance: 150 },
        { maneuver: { type: 'arrive' }, name: '', distance: 0 },
      ],
    },
    {
      steps: [
        { maneuver: { type: 'depart' }, name: 'B Road', distance: 100 },
        { maneuver: { type: 'arrive' }, name: '', distance: 0 },
      ],
    },
  ];
  const orderedPoints = [[0, 0], [1, 1], [2, 2]]; // Start, Stop 1, End

  const lines = buildDirections(legs, orderedPoints);

  assert.equal(lines.length, 5);
  assert.equal(lines[2].isStopMarker, true);
  assert.equal(lines[2].text, 'Arrive at Stop 1'); // legIdx 0 -> stopLabel(1, 3) = "Stop 1"
  assert.equal(lines[2].legIdx, 0);
  assert.equal(lines[4].isStopMarker, true);
  assert.equal(lines[4].text, 'Arrive at your destination'); // last leg -> final destination wording
  assert.equal(lines[4].legIdx, 1);
  assert.equal(lines[0].isStopMarker, false);
  assert.equal(lines[0].text, 'Head on A Road');
});

// ---------- Live re-optimization demo helpers ----------

test('advanceSimulatedHour: steps forward and wraps past midnight', () => {
  assert.equal(advanceSimulatedHour(9, 0.25), 9.25);
  const wrapped = advanceSimulatedHour(23.9, 0.25);
  assert.ok(wrapped >= 0 && wrapped < 1); // wrapped to just after midnight, not 24.15
  assert.ok(Math.abs(wrapped - 0.15) < 1e-9);
  assert.equal(advanceSimulatedHour(0, 0), 0);
});

test('shouldTriggerIncident: a simple deterministic threshold', () => {
  assert.equal(shouldTriggerIncident(0.1, 0.35), true);
  assert.equal(shouldTriggerIncident(0.35, 0.35), false); // boundary is exclusive
  assert.equal(shouldTriggerIncident(0.9, 0.35), false);
  assert.equal(shouldTriggerIncident(0, 0), false); // probability 0 never triggers
});

test('pickIncidentLeg: picks one of the stopCount-1 consecutive legs, deterministically from rngValue', () => {
  assert.deepEqual(pickIncidentLeg(4, 0.0), [0, 1]);
  assert.deepEqual(pickIncidentLeg(4, 0.99), [2, 3]); // last leg, never rounds past the end
  assert.deepEqual(pickIncidentLeg(4, 0.5), [1, 2]);
  assert.deepEqual(pickIncidentLeg(2, 0.7), [0, 1]); // only one possible leg
  assert.equal(pickIncidentLeg(1, 0.5), null); // fewer than 2 points -> no leg to pick
  assert.equal(pickIncidentLeg(0, 0.5), null);
});

test('describeLiveTick: reports a reroute honestly, including the incident leg and the real cost delta', () => {
  const rerouted = describeLiveTick({
    hour: 18.5, previousCost: 42.0, newCost: 39.5, orderChanged: true, incidentLeg: [1, 2],
  });
  assert.equal(rerouted.rerouted, true);
  assert.match(rerouted.message, /Simulated incident on leg 1→2/);
  assert.match(rerouted.message, /6:30 PM/);
  assert.match(rerouted.message, /rerouted/);
  assert.match(rerouted.message, /-2\.5 min/);

  const unchanged = describeLiveTick({
    hour: 9.0, previousCost: 20.0, newCost: 20.0, orderChanged: false, incidentLeg: null,
  });
  assert.equal(unchanged.rerouted, false);
  assert.doesNotMatch(unchanged.message, /Simulated incident/);
  assert.match(unchanged.message, /still best/);
  assert.match(unchanged.message, /0\.0 min/);
});

test('fleetOrderChanged: true when no previous snapshot exists yet', () => {
  assert.equal(fleetOrderChanged(null, [{ vehicle: 0, order: [0, 1, 2, 0] }]), true);
});

test('fleetOrderChanged: false when every vehicle kept its exact stop order', () => {
  const prev = [{ vehicle: 0, order: [0, 1, 2, 0] }, { vehicle: 1, order: [0, 3, 0] }];
  const next = [{ vehicle: 0, order: [0, 1, 2, 0] }, { vehicle: 1, order: [0, 3, 0] }];
  assert.equal(fleetOrderChanged(prev, next), false);
});

test('fleetOrderChanged: true when just one of several vehicles changed its order', () => {
  const prev = [{ vehicle: 0, order: [0, 1, 2, 0] }, { vehicle: 1, order: [0, 3, 0] }];
  const next = [{ vehicle: 0, order: [0, 2, 1, 0] }, { vehicle: 1, order: [0, 3, 0] }];
  assert.equal(fleetOrderChanged(prev, next), true);
});

test('fleetOrderChanged: true when the number of vehicles used changed', () => {
  const prev = [{ vehicle: 0, order: [0, 1, 2, 3, 0] }];
  const next = [{ vehicle: 0, order: [0, 1, 2, 0] }, { vehicle: 1, order: [0, 3, 0] }];
  assert.equal(fleetOrderChanged(prev, next), true);
});
