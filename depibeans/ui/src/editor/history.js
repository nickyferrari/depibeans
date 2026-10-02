// One undo/redo history of draft texts, shared by the graph, the script and every
// host action that calls checkpoint(). A history belongs to one draft: opening
// another experiment clears it.
import { HISTORY_LIMIT } from './constants.js';

export function createHistory(limit = HISTORY_LIMIT) {
  let undoStack = [];
  let redoStack = [];

  // Pops until a state different from `current` is found; the rest are no-ops
  // left by actions that checkpointed and then changed nothing.
  function travel(from, to, current) {
    let saved;
    do { saved = from.pop(); } while (saved !== undefined && saved === current);
    if (saved === undefined) return undefined;
    to.push(current);
    return saved;
  }

  return {
    // Records the draft as it is before a change. Returns whether a state was added.
    checkpoint(text) {
      if (!text) return false;
      const added = undoStack.at(-1) !== text;
      if (added) undoStack.push(text);
      if (undoStack.length > limit) undoStack.shift();
      redoStack = [];
      return added;
    },
    // Withdraws the checkpoint of a change that then failed.
    dropLast() { undoStack.pop(); },
    undo(current) { return travel(undoStack, redoStack, current); },
    redo(current) { return travel(redoStack, undoStack, current); },
    clear() { undoStack = []; redoStack = []; },
    get canUndo() { return undoStack.length > 0; },
    get canRedo() { return redoStack.length > 0; },
    get depth() { return undoStack.length; },
  };
}
