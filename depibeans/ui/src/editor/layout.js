// Page arrangement around the editor: the graph and script come first, generators
// are one collapsed section below them, and controls that only repeat what a field
// already does on commit are retired. Elements are moved, never recreated, so the
// host's own handlers and ids keep working.

function moveIfPresent(target, ...nodes) {
  for (const node of nodes) if (node) target.append(node);
}

export function arrangeEditorPage({ $, G, frame, bar, readout }) {
  const document = frame.ownerDocument;

  // "Add light change" / "Add measurement" join the editor's own toolbar.
  const addLight = G('light'), addMeasurement = G('capture'), typeLabel = $('graph-measurement-type')?.parentElement;
  if (addLight && addMeasurement) {
    const row = addLight.parentElement;
    const group = document.createElement('span');
    group.className = 'ge-add';
    addLight.textContent = '+ Light';
    addLight.title = 'Add a light change in the middle of the view';
    addMeasurement.textContent = '+ Measurement';
    addMeasurement.title = 'Add a measurement of the chosen type in the middle of the view';
    if (typeLabel) {
      for (const node of [...typeLabel.childNodes]) if (node.nodeType === 3) node.textContent = '';   // the select carries its own accessible name
      typeLabel.classList.add('ge-add-type');
    }
    moveIfPresent(group, addLight, typeLabel, addMeasurement);
    bar.insertBefore(group, readout);
    if (row && !row.querySelector('button:not([hidden]):not(#graph-undo), select, input')) row.hidden = true;
  }

  // Generators write events into the same draft; they are tools, not the main view.
  const profile = document.querySelector('.profile-components'), range = $('plain-range');
  if (profile) {
    const generators = document.createElement('details');
    generators.className = 'ge-generators';
    const summary = document.createElement('summary');
    summary.textContent = 'Generators · daily light profile and day range';
    generators.append(summary);
    moveIfPresent(generators, range, profile);
    frame.after(generators);
  }

  // The duration field applies itself when committed (Enter or leaving the field),
  // through the host's validation. A second button for the same action is noise.
  for (const button of document.querySelectorAll('#experiment-editor button')) {
    if (button.textContent.trim() === 'Apply duration') button.hidden = true;
  }
}
